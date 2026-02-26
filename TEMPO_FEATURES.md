# 🎉 Sistema de Feriados - App Tempo

## ✅ Funcionalidades Implementadas

### 1. **Diferenciação Visual no Calendário**
- ✅ **Sábados e Domingos**: Destacados em vermelho (`.weekend`)
- ✅ **Feriados**: Fundo vermelho gradiente com borda destacada (`.holiday`)
- ✅ **Data Atual**: Fundo azul gradiente com brilho

### 2. **Card de Feriados**
- ✅ Aparece automaticamente quando há feriados no período selecionado
- ✅ Mostra todos os feriados do mês (modo dias)
- ✅ Mostra todos os feriados do ano (modo meses)
- ✅ Oculto no modo décadas

### 3. **Tipos de Feriados Incluídos**

#### **Nacionais:**
- Confraternização Universal (1º Jan)
- Tiradentes (21 Abr)
- Dia do Trabalho (1º Mai)
- Independência do Brasil (7 Set)
- Nossa Senhora Aparecida (12 Out)
- Finados (2 Nov)
- Proclamação da República (15 Nov)
- Consciência Negra (20 Nov)
- Natal (25 Dez)
- Carnaval (móvel)
- Sexta-feira Santa (móvel)
- Corpus Christi (móvel)

#### **Estaduais - São Paulo:**
- Revolução Constitucionalista (9 Jul)

#### **Municipais:**
- **São Sebastião-SP**: São Sebastião (20 Jan)
- **Ubatuba-SP**: Aniversário de Ubatuba (3 Fev)

#### **Datas Comemorativas:**
- Dia dos Namorados (14 Fev)
- Dia Internacional da Mulher (8 Mar)
- Dia das Mães (12 Mai)
- Dia dos Namorados (13 Jun)
- São João (24 Jun)
- Dia dos Pais (11 Ago)
- Halloween (31 Out)
- Páscoa (móvel)
- Réveillon (31 Dez)´

### 4. **Cálculo Automático de Feriados Móveis**
- ✅ **Páscoa**: Calculada usando algoritmo de Computus
- ✅ **Carnaval**: 47 dias antes da Páscoa
- ✅ **Sexta-feira Santa**: 2 dias antes da Páscoa
- ✅ **Corpus Christi**: 60 dias após a Páscoa

### 5. **Atualização em Tempo Real**
- ✅ Sistema 100% gratuito
- ✅ Cálculos feitos no navegador (JavaScript)
- ✅ Sem necessidade de APIs externas
- ✅ Funciona offline

### 6. **Navegação Inteligente**
- ✅ **Modo Dias**: Mostra feriados do mês
- ✅ **Modo Meses**: Mostra todos os feriados do ano
- ✅ **Modo Anos**: Oculta card de feriados

## 📁 Arquivos Modificados

1. **`app.py`**: Rota `/tempo` modificada para carregar HTML externo
2. **`templates/tempo.html`**: Arquivo completo com sistema de feriados

## 🚀 Como Usar

1. Acesse `http://localhost:5000/tempo`
2. Navegue pelos meses/anos usando as setas
3. Clique no título para alternar entre dias/meses/anos
4. Feriados aparecem automaticamente destacados
5. Card de feriados mostra detalhes de cada data

## 🎨 Estilos Visuais

- **Finais de Semana**: Texto vermelho
- **Feriados**: Fundo vermelho gradiente + borda vermelha
- **Card de Feriados**: Borda esquerda vermelha + ícone 🎉
- **Informações**: Data, nome e tipo do feriado

## 🔄 Manutenção

Para adicionar novos feriados, edite o array `holidays.fixed` em `templates/tempo.html`:

```javascript
{day: DD, month: MM, name: 'Nome do Feriado', type: 'Tipo'}
```

Onde:
- `day`: Dia do mês (1-31)
- `month`: Mês (1-12)
- `name`: Nome do feriado
- `type`: 'Nacional', 'Estadual - SP', 'Municipal - Cidade', 'Comemorativa'
