"""Motor de IA generativa do Efeito Matcha real: Stable Diffusion (img2img) +
ControlNet SoftEdge, replicando localmente o pipeline usado pelo filtro viral
"Wild Hearts Whisper" (TikTok/CapCut) descrito pelo usuário.

Import deste módulo é sempre leve — torch/diffusers/controlnet_aux só são
importados dentro das funções, e só quando alguém realmente usa o recurso.
Assim o Verto continua abrindo normalmente em máquinas sem essas dependências
pesadas instaladas (ver requirements_ai.txt, instalado à parte, sob demanda).

A geração em si roda num processo-filho separado (multiprocessing), não numa
thread: sem GPU, carregar SD1.5 + ControlNet em float32 consome vários GB de
RAM, e em máquinas com pouca memória livre o kernel mata o processo (OOM
killer) no meio do carregamento. Se isso rodasse na mesma thread/processo do
Flask, o servidor inteiro caía e o navegador só via "Failed to fetch" sem
explicação. Isolado num processo-filho, o OOM kill derruba só o worker — o
Flask continua de pé e consegue reportar um erro claro ao usuário. O worker
fica vivo entre gerações (o modelo carregado é reaproveitado), e é
reiniciado automaticamente se cair.
"""
import base64
import io
import multiprocessing
import queue
import signal
import threading
import time
import traceback
import uuid

_LOCK = threading.Lock()
_PIPE = None
_PREPROCESSOR = None
_LOAD_ERROR = None

_JOBS = {}
_JOBS_LOCK = threading.Lock()

_WORKER = None
_WORKER_LOCK = threading.Lock()

# DreamShaper v8 (mirror ungated no Hugging Face) — o checkpoint SD1.5
# recomendado no guia por dar bons resultados de rosto/textura fluida.
MODEL_ID = "Lykon/dreamshaper-8"
# ControlNet v1.1 SoftEdge — o mesmo tipo de controle citado no guia
# (softedge_pidinet) para não deformar rosto/silhueta original.
CONTROLNET_ID = "lllyasviel/control_v11p_sd15_softedge"
ANNOTATOR_ID = "lllyasviel/Annotators"

ADD_PROMPT = (
    "an artistic fluid art masterpiece, melting liquid texture, creamy matcha swirls, "
    "glossy jade and milk foam overlays, smooth swirls, soft lighting, pastel green tint, "
    "hyperdetailed digital art, high quality"
)
ADD_NEGATIVE = (
    "ugly, deformed, photorealistic, bad anatomy, dark colors, high contrast, sharp lines, "
    "noise, text, watermark"
)
# Prompt inverso: não existe "desfazer" matemático de uma geração por difusão,
# então a remoção também é uma geração — só que guiada para o lado oposto
# (foto normal, sem tingimento nem textura de fluido) em vez do lado matcha.
REMOVE_PROMPT = (
    "a normal everyday photo, natural skin tones, realistic accurate colors, "
    "regular photography lighting, sharp focus, unedited photograph, high detail"
)
REMOVE_NEGATIVE = (
    "green tint, matcha, swirls, fluid art, painting, illustration, surreal, fantasy, "
    "melted, liquid texture, blurry, oversaturated, jade, foam"
)


def is_available():
    try:
        import torch  # noqa: F401
        import diffusers  # noqa: F401
        import controlnet_aux  # noqa: F401
        return True
    except Exception:
        return False


def install_instructions():
    return (
        "Recursos de IA generativa (Stable Diffusion + ControlNet) não estão instalados. "
        "Rode no terminal, dentro da pasta do Verto:\n"
        "pip install -r MatchaEffect/requirements_ai.txt\n"
        "Aviso: são vários GB de download (PyTorch + modelos) na primeira execução, "
        "e sem GPU NVIDIA cada imagem pode levar alguns minutos para gerar."
    )


def has_cuda():
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _load_pipeline():
    global _PIPE, _PREPROCESSOR, _LOAD_ERROR
    if _PIPE is not None:
        return
    with _LOCK:
        if _PIPE is not None:
            return
        try:
            import torch
            from diffusers import StableDiffusionControlNetImg2ImgPipeline, ControlNetModel
            from controlnet_aux import PidiNetDetector

            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32

            controlnet = ControlNetModel.from_pretrained(CONTROLNET_ID, torch_dtype=dtype)
            pipe = StableDiffusionControlNetImg2ImgPipeline.from_pretrained(
                MODEL_ID, controlnet=controlnet, torch_dtype=dtype, safety_checker=None,
            )
            pipe = pipe.to(device)
            if device == "cpu":
                pipe.enable_attention_slicing()

            _PREPROCESSOR = PidiNetDetector.from_pretrained(ANNOTATOR_ID)
            _PIPE = pipe
        except Exception as e:
            _LOAD_ERROR = str(e)
            raise


def _run_pipeline(image_bytes, prompt, negative_prompt, denoising_strength,
                   control_weight, steps, cfg, seed, max_side=512):
    from PIL import Image
    import torch

    _load_pipeline()

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    scale = max_side / max(w, h)
    if scale < 1:
        img = img.resize((max(64, int(w * scale)), max(64, int(h * scale))), Image.LANCZOS)
    # Stable Diffusion espera dimensões múltiplas de 8
    nw = max(64, (img.width // 8) * 8)
    nh = max(64, (img.height // 8) * 8)
    if (nw, nh) != img.size:
        img = img.resize((nw, nh))

    # PidiNetDetector por padrão redimensiona a saída sozinho (image_resolution=512,
    # baseado no lado MENOR da imagem) — diferente do redimensionamento acima (baseado
    # no lado MAIOR, via max_side). Para uma imagem não quadrada isso produz um
    # control_image com tamanho e proporção diferentes de img, e o ControlNet quebra
    # ao somar os tensores (dimensões de latent incompatíveis). Forçamos o mesmo
    # tamanho exato de img para as duas entradas ficarem alinhadas.
    control_image = _PREPROCESSOR(img, detect_resolution=max(img.size), image_resolution=max(img.size))
    if control_image.size != img.size:
        control_image = control_image.resize(img.size, Image.LANCZOS)

    generator = None
    if seed is not None:
        generator = torch.Generator(device=_PIPE.device).manual_seed(int(seed))

    result = _PIPE(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=img,
        control_image=control_image,
        strength=denoising_strength,
        controlnet_conditioning_scale=control_weight,
        num_inference_steps=steps,
        guidance_scale=cfg,
        generator=generator,
    ).images[0]

    return result


def _worker_main(in_q, out_q):
    """Loop do processo-filho: recebe pedidos de geração, mantém o modelo
    carregado entre eles e devolve o resultado (ou erro) por fila."""
    while True:
        msg = in_q.get()
        if msg is None:
            break
        job_id, mode, image_bytes, params = msg
        try:
            prompt = ADD_PROMPT if mode == 'add' else REMOVE_PROMPT
            negative = ADD_NEGATIVE if mode == 'add' else REMOVE_NEGATIVE
            result_img = _run_pipeline(
                image_bytes, prompt, negative,
                params['denoising_strength'], params['control_weight'],
                params['steps'], params['cfg'], params.get('seed'),
                max_side=params.get('max_side', 512),
            )
            buf = io.BytesIO()
            result_img.save(buf, format='PNG')
            image_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
            out_q.put((job_id, 'done', image_b64, None))
        except Exception as e:
            out_q.put((job_id, 'error', None, f'{e}\n{traceback.format_exc()}'))


def _ensure_worker():
    """Garante um processo-filho vivo, reiniciando-o se tiver caído (ex.: OOM kill)."""
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is not None and _WORKER['process'].is_alive():
            return _WORKER
        ctx = multiprocessing.get_context('spawn')
        in_q = ctx.Queue()
        out_q = ctx.Queue()
        proc = ctx.Process(target=_worker_main, args=(in_q, out_q), daemon=True)
        proc.start()
        _WORKER = {'process': proc, 'in_q': in_q, 'out_q': out_q}
        return _WORKER


def _crash_message(exitcode):
    if exitcode is not None and exitcode < 0:
        try:
            sig_name = signal.Signals(-exitcode).name
        except ValueError:
            sig_name = str(-exitcode)
        if -exitcode == signal.SIGKILL:
            return (
                'O processo de geração foi encerrado pelo sistema operacional antes de '
                'terminar — quase sempre por falta de memória RAM disponível para carregar '
                'o modelo de IA (Stable Diffusion + ControlNet em CPU usam vários GB). '
                'Feche outros programas/abas para liberar memória e tente novamente, ou '
                'reduza a resolução (max_side) na configuração avançada.'
            )
        return f'O processo de geração foi encerrado inesperadamente (sinal {sig_name}).'
    return f'O processo de geração encerrou inesperadamente (código de saída {exitcode}).'


def _job_worker(job_id, mode, image_bytes, params):
    job = _JOBS[job_id]
    job['status'] = 'running'
    try:
        job['message'] = 'Carregando modelo de IA (pode levar 1-2 min na primeira vez, e baixar vários GB no 1º uso)...'
        worker = _ensure_worker()
        worker['in_q'].put((job_id, mode, image_bytes, params))
        job['message'] = 'Gerando com Stable Diffusion + ControlNet (pode levar vários minutos sem GPU)...'

        while True:
            try:
                result_id, status, image_b64, err = worker['out_q'].get(timeout=1)
            except queue.Empty:
                # Só declara o worker morto se a fila realmente não tiver mais nada
                # para entregar — evita perder um resultado que chegou bem na hora
                # em que o processo estava encerrando.
                if not worker['process'].is_alive():
                    raise RuntimeError(_crash_message(worker['process'].exitcode))
                continue
            if result_id != job_id:
                # Resultado de outro job (não deveria ocorrer, geração é serial) — ignora.
                continue
            if status == 'error':
                raise RuntimeError(err)
            job['image_b64'] = image_b64
            job['status'] = 'done'
            job['message'] = 'Concluído.'
            break
    except Exception as e:
        job['status'] = 'error'
        job['message'] = f'Erro ao gerar: {e}'
        job['traceback'] = traceback.format_exc()
    finally:
        job['elapsed'] = round(time.time() - job['started_at'], 1)


def start_job(mode, image_bytes, params):
    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            'status': 'queued',
            'message': 'Na fila...',
            'started_at': time.time(),
            'image_b64': None,
        }
    t = threading.Thread(target=_job_worker, args=(job_id, mode, image_bytes, params), daemon=True)
    t.start()
    return job_id


def get_job(job_id):
    return _JOBS.get(job_id)
