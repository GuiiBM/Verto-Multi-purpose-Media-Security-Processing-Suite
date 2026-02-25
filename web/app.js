const form = document.getElementById('download-form');
const button = document.getElementById('download-button');
const btnText = document.querySelector('.btn-text');
const spinner = document.getElementById('btn-spinner');
const status = document.getElementById('status');
const urlInput = document.getElementById('url');
const preview = document.getElementById('preview');
const previewLoading = document.getElementById('preview-loading');
const previewContent = document.getElementById('preview-content');
const previewThumb = document.getElementById('preview-thumb');
const previewTitle = document.getElementById('preview-title');
const previewDuration = document.getElementById('preview-duration');
const previewPlayer = document.getElementById('preview-player');
const qualitySelect = document.getElementById('quality');
const qualityLabel = document.getElementById('quality-label');

let debounceTimer;
let currentVideoId = '';
let currentFormat = 'mp4';

const formatBtns = document.querySelectorAll('.format-btn');

formatBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        formatBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFormat = btn.dataset.format;
        updateQualityOptions();
        resetPreviewToThumb();
    });
});

function resetPreviewToThumb() {
    if (previewPlayer && previewThumb) {
        previewPlayer.style.display = 'none';
        previewPlayer.innerHTML = '';
        previewThumb.style.display = 'block';
        if (currentFormat === 'thumbnail' || currentFormat === 'jpg') {
            previewThumb.className = 'image-format';
        } else {
            previewThumb.className = '';
        }
    }
}

function updateQualityOptions() {
    let options;
    if (currentFormat === 'mp3') {
        options = mp3Options;
    } else if (currentFormat === 'thumbnail') {
        options = thumbnailOptions;
    } else if (currentFormat === 'jpg') {
        options = thumbnailOptions.map(opt => ({
            value: opt.value,
            text: opt.text
        }));
    } else {
        options = mp4Options;
    }
    qualitySelect.innerHTML = options.map(opt => {
        let sizeKey = opt.value;
        if (currentFormat === 'jpg') {
            sizeKey = opt.value + '_jpg';
        }
        const size = formatSizes[sizeKey] || '';
        return `<option value="${opt.value}">${opt.text}${size}</option>`;
    }).join('');
}

let debounceTimer;
let currentVideoId = '';
let currentFormat = 'mp4';

const mp4Options = [
    { value: 'best', text: '🔥 Melhor qualidade disponível' },
    { value: '1080p', text: '📺 1080p (Full HD)' },
    { value: '720p', text: '📱 720p (HD)' },
    { value: '480p', text: '💻 480p (SD)' },
    { value: '360p', text: '📞 360p (Baixa)' }
];

const mp3Options = [
    { value: 'best', text: '🔥 Melhor qualidade disponível' },
    { value: '320', text: '📺 320 kbps (Alta)' },
    { value: '256', text: '📱 256 kbps' },
    { value: '192', text: '💻 192 kbps (Média)' },
    { value: '128', text: '📞 128 kbps (Baixa)' },
    { value: 'worst', text: '⚡ Menor arquivo (pior qualidade)' }
];

const thumbnailOptions = [
    { value: 'maxres', text: '🔥 Máxima resolução' },
    { value: 'high', text: '📺 Alta qualidade' },
    { value: 'medium', text: '📱 Média qualidade' },
    { value: 'default', text: '📞 Padrão' }
];

let formatSizes = {};

function formatBytes(bytes) {
    if (bytes === 0) return '';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return ' - ' + parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function playVideo() {
    if (currentFormat === 'thumbnail' || currentFormat === 'jpg') {
        const modal = document.getElementById('image-modal');
        const modalImage = document.getElementById('modal-image');
        modalImage.src = previewThumb.src;
        modal.style.display = 'flex';
    } else {
        previewThumb.style.display = 'none';
        previewPlayer.style.display = 'block';
        previewPlayer.innerHTML = `<iframe src="https://www.youtube.com/embed/${currentVideoId}?autoplay=1" allow="autoplay; encrypted-media" allowfullscreen></iframe>`;
    }
}

function closeImageModal() {
    document.getElementById('image-modal').style.display = 'none';
}

urlInput.addEventListener('input', (e) => {
    clearTimeout(debounceTimer);
    const url = e.target.value.trim();
    const previewCard = document.getElementById('preview-card');
    
    if (!url || !isYouTubeUrl(url)) {
        previewCard.classList.remove('show');
        return;
    }
    
    debounceTimer = setTimeout(() => loadPreview(url), 800);
});

function isYouTubeUrl(url) {
    return /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\/.+/.test(url);
}

async function loadPreview(url) {
    const previewCard = document.getElementById('preview-card');
    previewCard.classList.add('show');
    previewLoading.style.display = 'block';
    previewContent.style.display = 'none';
    
    try {
        const response = await fetch('/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        
        const result = await response.json();
        
        if (result.success) {
            currentVideoId = result.video_id;
            previewThumb.src = result.thumbnail;
            previewThumb.style.display = 'block';
            if (currentFormat === 'thumbnail' || currentFormat === 'jpg') {
                previewThumb.className = 'image-format';
            } else {
                previewThumb.className = '';
            }
            previewPlayer.style.display = 'none';
            previewPlayer.innerHTML = '';
            previewTitle.textContent = result.title;
            previewDuration.textContent = `Duração: ${result.duration}`;
            previewLoading.style.display = 'none';
            previewContent.style.display = 'block';
            
            // Buscar tamanhos dos formatos se houver endpoint
            if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
                loadFormatSizes(url);
            }
        } else {
            previewCard.classList.remove('show');
        }
    } catch (error) {
        previewCard.classList.remove('show');
    }
}

async function loadFormatSizes(url) {
    try {
        const response = await fetch('/formats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        
        const result = await response.json();
        
        if (result.success && result.sizes) {
            formatSizes = {};
            Object.keys(result.sizes).forEach(key => {
                formatSizes[key] = formatBytes(result.sizes[key]);
            });
            updateQualityOptions();
        }
    } catch (error) {
        console.log('Erro ao carregar tamanhos');
    }
}

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const url = document.getElementById('url').value.trim();
    const format = currentFormat;
    const quality = qualitySelect.value;
    
    if (!url) {
        showError('Insira uma URL válida.');
        return;
    }

    setLoading(true);
    
    try {
        const response = await fetch('/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url, format, quality })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showSuccess(result.message);
        } else {
            showError(result.error);
        }
    } catch (error) {
        showError('Erro de conexão: ' + error.message);
    } finally {
        setLoading(false);
    }
});

function showSuccess(message) {
    status.className = 'status ok';
    status.textContent = message;
}

function showError(message) {
    status.className = 'status err';
    status.textContent = message;
}

function setLoading(loading) {
    button.disabled = loading;
    
    if (loading) {
        btnText.textContent = 'Converting...';
        spinner.style.display = 'inline-block';
    } else {
        btnText.textContent = '⬇️ Download';
        spinner.style.display = 'none';
    }
}