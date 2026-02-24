const form = document.getElementById('download-form');
const button = document.getElementById('download-button');
const btnText = document.querySelector('.btn-text');
const spinner = document.getElementById('btn-spinner');
const status = document.getElementById('status');

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const url = document.getElementById('url').value.trim();
    const quality = document.getElementById('quality').value;
    
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
            body: JSON.stringify({ url, quality })
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
        btnText.textContent = 'Baixando...';
        spinner.style.display = 'inline-block';
    } else {
        btnText.textContent = '⬇️ Baixar MP4';
        spinner.style.display = 'none';
    }
}