# 🎮 Bot Automático Roblox - Busca Faixa Laranja + Arremesso (+20) + Barra 2X

Bot externo em Python com **Visão Computacional em Tempo Real (60+ FPS)** e interface gráfica (`Tkinter`), desenvolvido para automatizar o ciclo de caminhada até a faixa laranja de chegada, arremesso no topo da barra (`+20`), pulo de animação (`TAP TO SKIP`) e clique automático no bônus roxo `x2` durante o treino de barra.

---

## ✨ Funcionalidades

1. **Busca Automática da Faixa Laranja (Visão Computacional):**
   - Após o teleporte de retorno ao cercado, gira a câmera em pulsos curtos controlados até localizar e centralizar a faixa laranja/brilhante de chegada.
   - Anda automaticamente até a faixa laranja e para assim que a barra de força (**`TAP TO THROW!`**) abre na tela.
2. **Arremesso de Alta Precisão no `+20`:**
   - Detecta a barra vertical pelas 3 zonas de cor simultâneas (verde no topo, amarelo no meio e laranja/vermelho na base), evitando falsos positivos com o cenário.
   - Rastreia a barrinha branca do medidor e clica no exato milissegundo em que ela atinge o topo (`+20`).
3. **Auto `TAP TO SKIP`:**
   - Após o arremesso, clica automaticamente para pular a animação quando um animal é capturado, acelerando o retorno para o cercado.
4. **💪 Auto-Click no Bônus Roxo `x2` (Treino de Barra):**
   - Detecta automaticamente quando o personagem está treinando na barra (botão vermelho `STOP` ativo).
   - Monitora a tela inteira e clica instantaneamente em cima do **círculo roxo com o dedo amarelo (`x2`)** sempre que ele aparece em qualquer posição da tela.
5. **3 Modos de Execução (Alt+Tab / Segundo Plano):**
   - **Híbrido (Recomendado):** Captura a janela do Roblox em segundo plano via `PrintWindow` e foca rapidamente para enviar comandos via *DirectInput ScanCode* sem bloqueio.
   - **Segundo Plano Puro:** Envia mensagens `PostMessage` (`WM_KEYDOWN` / `WM_LBUTTONDOWN`) diretamente para o `HWND` da janela do Roblox (mantenha a janela aberta atrás de outras janelas, sem minimizar na barra de tarefas).
   - **Janela Focada:** Uso com a tela do Roblox ativa.

---

## 🚀 Como Instalar e Rodar

### Pré-requisitos
- Windows 10 ou 11
- [Python 3.10+](https://www.python.org/downloads/) instalado

### 1. Clonar o repositório
```bash
git clone https://github.com/CaioSrf/roblox-throw-bot.git
cd roblox-throw-bot
```

### 2. Instalar as dependências
```bash
pip install -r requirements.txt
```

### 3. Executar o Bot
Dê dois cliques no arquivo **`INICIAR_BOT.bat`** ou execute pelo terminal:
```bash
python bot_roblox.py
```

---

## ⌨️ Atalhos Globais
- **`F8`**: Iniciar / Pausar o bot a qualquer momento.
- **`F9`**: Iniciar / Parar gravação do tempo de caminhada (opcional).
