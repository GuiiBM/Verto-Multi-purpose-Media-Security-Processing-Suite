# 📋 PASSO A PASSO - YouTube MP4 Downloader

## 🚀 Instalação e Primeiro Uso

### Passo 1: Verificar Python
1. Abra o **Prompt de Comando** (cmd)
2. Digite: `python --version`
3. Se não aparecer a versão, instale o Python em: https://python.org

### Passo 2: Instalar Dependências
1. Vá para a pasta `executaveis/`
2. **Clique duas vezes** em `INSTALAR_DEPENDENCIAS.bat`
3. Aguarde a instalação terminar

### Passo 3: Iniciar Aplicação
1. **Clique duas vezes** em `INICIAR.bat`
2. Aguarde aparecer: "Running on http://127.0.0.1:5000"
3. Abra seu navegador e acesse: `http://localhost:5000`

## 🎯 Como Usar

### 1. Baixar Vídeo
1. Cole a URL do YouTube no campo
2. Escolha a qualidade desejada:
   - **🔥 Melhor qualidade**: Maior qualidade disponível
   - **📺 1080p**: Full HD (recomendado)
   - **📱 720p**: HD (boa qualidade, arquivo menor)
   - **💻 480p**: Qualidade padrão
   - **📞 360p**: Qualidade baixa
   - **⚡ Menor arquivo**: Pior qualidade, arquivo muito pequeno
3. Clique em "Baixar MP4"
4. Aguarde o download terminar
5. O arquivo será salvo na pasta `downloads/`

### 2. Parar o Servidor
- No terminal, pressione `Ctrl + C`
- Ou feche a janela do terminal

## 🔧 Solução de Problemas

### Erro 403 Forbidden
1. Execute `ATUALIZAR_YT-DLP.bat`
2. Reinicie a aplicação
3. Tente novamente

### Python não encontrado
1. Instale o Python: https://python.org
2. Marque "Add to PATH" durante a instalação
3. Reinicie o computador

### Dependências não instaladas
1. Execute `INSTALAR_DEPENDENCIAS.bat` novamente
2. Verifique sua conexão com a internet

## 📁 Arquivos Importantes

```
executaveis/
├── INICIAR.bat                    # ← CLIQUE AQUI PARA INICIAR
├── INSTALAR_DEPENDENCIAS.bat     # Instala tudo automaticamente
└── ATUALIZAR_YT-DLP.bat         # Corrige erro 403
```

## ⚠️ Notas Importantes

- **Mantenha o terminal aberto** enquanto usa a aplicação
- Os vídeos ficam salvos na pasta `downloads/`
- Funciona apenas com vídeos **públicos** do YouTube
- **Respeite os direitos autorais** dos conteúdos
- Se der erro, tente com outro vídeo primeiro

## 🆘 Precisa de Ajuda?

1. Certifique-se que o Python está instalado
2. Execute `INSTALAR_DEPENDENCIAS.bat`
3. Se persistir erro 403, execute `ATUALIZAR_YT-DLP.bat`
4. Reinicie a aplicação com `INICIAR.bat`