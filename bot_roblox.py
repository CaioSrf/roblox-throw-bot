# -*- coding: utf-8 -*-
"""
Bot Automático para Roblox - Busca Inteligente da Faixa Laranja + Arremesso (+20) + Tap to Skip + Barra 2X
===========================================================================================================
Novidades e Correções desta versão:
1. Correção do Giro da Câmera e Detecção da Faixa Laranja:
   - Pulsos curtos e controlados na câmera ao procurar a faixa laranja, parando imediatamente
     assim que a faixa laranja aparecer na tela (ex: ~27511 px, X=0.53).
   - Removida a correção de setas durante a caminhada que fazia o personagem girar em círculos.
   - Proteção contra falso positivo na barra de arremesso ("ESTADO: ARREMESSANDO" agora exige
     as 3 cores da barra vertical — verde no topo, amarelo no meio e laranja/vermelho embaixo).
2. Auto-Click no Círculo Roxo "x2" (Treino de Barra / Pull-ups):
   - Detecta automaticamente quando você está fazendo barra (botão vermelho STOP + barra de Level).
   - Enquanto você estiver fazendo barra, o bot NÃO tenta andar; ele monitora a tela inteira em
     alta velocidade e, sempre que o círculo redondo roxo com a mãozinha amarela ("x2") aparecer
     (em qualquer posição da tela!), ele clica exatamente em cima do círculo automaticamente!
3. Auto "TAP TO SKIP" após o Arremesso:
   - Após arremessar no +20, o bot clica periodicamente no centro da tela para acionar o
     "TAP TO SKIP" quando você captura um animal, acelerando o retorno para o cercado, e
     só volta a procurar a faixa laranja quando realmente tiver retornado ao cercado!
"""

import ctypes
import json
import os
import threading
import time
import tkinter as tk
from tkinter import ttk

import keyboard
import mss
import numpy as np
from PIL import Image, ImageTk
import win32api
import win32con
import win32gui
import win32ui

# Garantir DPI Awareness para capturar coordenadas exatas da janela do Roblox no Windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_bot.json")

# =====================================================================
# SIMULAÇÃO DE INPUT (DIRECTINPUT SCAN CODES & WIN32 POSTMESSAGE)
# =====================================================================
SendInput = ctypes.windll.user32.SendInput
PUL = ctypes.POINTER(ctypes.c_ulong)


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class Input_I(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput),
    ]


class Input(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ii", Input_I),
    ]


KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

VK_MAP = {
    "w": (0x57, 0x11, False),
    "a": (0x41, 0x1E, False),
    "s": (0x53, 0x1F, False),
    "d": (0x44, 0x20, False),
    "space": (0x20, 0x39, False),
    "left": (win32con.VK_LEFT, 0x4B, True),
    "right": (win32con.VK_RIGHT, 0x4D, True),
    "up": (win32con.VK_UP, 0x48, True),
    "down": (win32con.VK_DOWN, 0x50, True),
}


def send_direct_key(key_name: str, down: bool):
    """Envia tecla via DirectInput ScanCode (funciona 100% no Roblox quando focado)."""
    vk, scan, is_ext = VK_MAP[key_name]
    flags = KEYEVENTF_SCANCODE
    if is_ext:
        flags |= KEYEVENTF_EXTENDEDKEY
    if not down:
        flags |= KEYEVENTF_KEYUP
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))


def send_background_key(hwnd: int, key_name: str, down: bool):
    """Envia tecla diretamente para a janela do Roblox em segundo plano via Win32 API."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return
    vk, scan, is_ext = VK_MAP[key_name]
    lparam = (scan << 16) | 1
    if is_ext:
        lparam |= (1 << 24)
    if not down:
        lparam |= (1 << 30) | (1 << 31)
        msg = win32con.WM_KEYUP
    else:
        msg = win32con.WM_KEYDOWN
    win32api.PostMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
    win32api.PostMessage(hwnd, msg, vk, lparam)


def click_at_normalized_pos(hwnd: int, norm_x: float, norm_y: float, mode: str, restore_window: bool = True, also_press_space: bool = False):
    """
    Clica em uma posição normalizada (0.0 a 1.0) dentro da área cliente da janela do Roblox.
    Usado tanto para:
    - Arremessar no +20 ("TAP TO THROW!")
    - Pular animação ("TAP TO SKIP")
    - Clicar exatamente em cima do círculo roxo "x2" na barra!
    """
    if not hwnd or not win32gui.IsWindow(hwnd):
        return

    try:
        crect = win32gui.GetClientRect(hwnd)
        cw = max(1, crect[2] - crect[0])
        ch = max(1, crect[3] - crect[1])
        client_x = int(cw * norm_x)
        client_y = int(ch * norm_y)
        screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))
    except Exception:
        return

    if mode == "background":
        lparam = win32api.MAKELONG(client_x, client_y)
        win32api.PostMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_CLICKACTIVE, 0)
        win32api.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
        win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
        if also_press_space:
            send_background_key(hwnd, "space", True)
        time.sleep(0.025)
        win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
        if also_press_space:
            send_background_key(hwnd, "space", False)
    else:
        prev_hwnd = win32gui.GetForegroundWindow()
        prev_pos = win32api.GetCursorPos()
        need_switch = (prev_hwnd != hwnd)

        if need_switch:
            try:
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                win32gui.SetForegroundWindow(hwnd)
                ctypes.windll.user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.012)
            except Exception:
                pass

        win32api.SetCursorPos((screen_x, screen_y))
        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        # Pequeno movimento relativo (1px) para o motor do Roblox atualizar o hover do botão UI
        ii_.mi = MouseInput(1, 1, 0, MOUSEEVENTF_MOVE, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(0), ii_)
        SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
        time.sleep(0.01)

        ii_.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(0), ii_)
        SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
        if also_press_space:
            send_direct_key("space", True)

        time.sleep(0.03)

        ii_.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, ctypes.pointer(extra))
        x = Input(ctypes.c_ulong(0), ii_)
        SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
        if also_press_space:
            send_direct_key("space", False)

        if need_switch and restore_window and prev_hwnd and win32gui.IsWindow(prev_hwnd):
            try:
                time.sleep(0.015)
                win32api.SetCursorPos(prev_pos)
                ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                win32gui.SetForegroundWindow(prev_hwnd)
                ctypes.windll.user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
            except Exception:
                pass


# =====================================================================
# CAPTURA DE TELA DA JANELA DO ROBLOX (BACKGROUND & FOREGROUND)
# =====================================================================
def find_roblox_hwnd() -> int:
    """Encontra o HWND da janela do Roblox Player."""
    target = []

    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title == "Roblox":
                target.append(hwnd)

    win32gui.EnumWindows(enum_cb, None)
    if target:
        return target[0]

    def enum_cb2(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if "roblox" in title.lower() and "bot" not in title.lower() and "studio" not in title.lower():
                target.append(hwnd)

    win32gui.EnumWindows(enum_cb2, None)
    return target[0] if target else 0


def capture_window_rgb(hwnd: int, sct: mss.mss) -> np.ndarray | None:
    """Captura a área cliente da janela do Roblox mesmo em segundo plano."""
    if not hwnd or not win32gui.IsWindow(hwnd) or win32gui.IsIconic(hwnd):
        return None

    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        w = right - left
        h = bottom - top
        if w < 200 or h < 200:
            return None

        hwndDC = win32gui.GetDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(saveBitMap)

        res = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)
        bmpstr = saveBitMap.GetBitmapBits(True)
        img = np.frombuffer(bmpstr, dtype=np.uint8).reshape((h, w, 4))

        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)

        if res == 1 and np.mean(img[:, :, :3]) > 5.0:
            return img[:, :, [2, 1, 0]].copy()
    except Exception:
        pass

    try:
        pt = win32gui.ClientToScreen(hwnd, (0, 0))
        rect = win32gui.GetClientRect(hwnd)
        w = rect[2] - rect[0]
        h = rect[3] - rect[1]
        monitor = {"left": pt[0], "top": pt[1], "width": w, "height": h}
        raw = np.array(sct.grab(monitor))
        return raw[:, :, [2, 1, 0]].copy()
    except Exception:
        return None


# =====================================================================
# VISÃO COMPUTACIONAL COMPLETA:
# 1) Treino de Barra (Botão STOP + Círculo Roxo x2 com mão amarela)
# 2) Barra Vertical de Arremesso (+20)
# 3) Faixa Laranja de Chegada
# =====================================================================
def analyze_frame(arr: np.ndarray):
    h, w, _ = arr.shape

    # -----------------------------------------------------------------
    # 1. DETECÇÃO DO TREINO DE BARRA (Botão vermelho "STOP" na parte inferior)
    # -----------------------------------------------------------------
    stop_box = arr[int(0.805 * h):int(0.865 * h), int(0.445 * w):int(0.555 * w)]
    red_ratio = np.mean((stop_box[:, :, 0] > 195) & (stop_box[:, :, 1] < 45) & (stop_box[:, :, 2] < 45))
    is_pullup = bool(red_ratio > 0.28)

    # -----------------------------------------------------------------
    # 2. DETECÇÃO DO CÍRCULO ROXO "x2" COM DEDO AMARELO (Aparece na Barra)
    # -----------------------------------------------------------------
    x2_pos = None
    # Procura em toda a região útil da tela para funcionar mesmo que o círculo mude de lugar!
    roi_y0, roi_y1 = int(0.12 * h), int(0.80 * h)
    roi_x0, roi_x1 = int(0.16 * w), int(0.84 * w)
    sub = arr[roi_y0:roi_y1:2, roi_x0:roi_x1:2]  # Subamostragem 2x para velocidade extrema
    sR = sub[:, :, 0].astype(np.int16)
    sG = sub[:, :, 1].astype(np.int16)
    sB = sub[:, :, 2].astype(np.int16)

    # Roxo/lilás do círculo redondo
    purple_mask = (sR > 165) & (sR < 248) & (sG > 50) & (sG < 175) & (sB > 210) & ((sB - sG) > 70) & ((sR - sG) > 50)
    # Amarelo/dourado da mãozinha com o dedo apontando dentro do círculo
    yellow_hand = (sR > 240) & (sG > 190) & (sG < 238) & (sB > 60) & (sB < 165) & ((sR - sB) > 85)

    scale_sub = (512 * 288) / float(max(1, sub.shape[0] * sub.shape[1]))
    if np.sum(purple_mask) * scale_sub > 90 and np.sum(yellow_hand) * scale_sub > 18:
        hy, hx = np.where(yellow_hand)
        # Usa a mediana dos pixels amarelos da mão para achar o centro exato do dedo
        cy_sub = int(np.median(hy))
        cx_sub = int(np.median(hx))
        rad = max(12, int(0.055 * sub.shape[1]))
        y_min, y_max = max(0, cy_sub - rad), min(sub.shape[0], cy_sub + rad)
        x_min, x_max = max(0, cx_sub - rad), min(sub.shape[1], cx_sub + rad)
        local_purple = np.sum(purple_mask[y_min:y_max, x_min:x_max]) * scale_sub
        if local_purple > 110:
            norm_x = (roi_x0 + cx_sub * 2) / float(w)
            norm_y = (roi_y0 + cy_sub * 2) / float(h)
            x2_pos = (float(norm_x), float(norm_y))

    # -----------------------------------------------------------------
    # 3. VERIFICAÇÃO RIGOROSA DA BARRA DE ARREMESSO ("TAP TO THROW!")
    # Exige simultaneamente: topo verde + meio amarelo + base laranja-avermelhada
    # Isso impede 100% que a faixa laranja no chão seja confundida com a barra vertical!
    # -----------------------------------------------------------------
    top_slice = arr[int(0.18 * h):int(0.32 * h), int(0.49 * w):int(0.51 * w)]
    mid_slice = arr[int(0.45 * h):int(0.53 * h), int(0.49 * w):int(0.51 * w)]
    bot_slice = arr[int(0.64 * h):int(0.71 * h), int(0.49 * w):int(0.51 * w)]

    top_ok = np.mean(
        ((top_slice[:, :, 1] > 215) & (top_slice[:, :, 0] < 175) & (top_slice[:, :, 2] < 145))
        | ((top_slice[:, :, 0] > 230) & (top_slice[:, :, 1] > 230) & (top_slice[:, :, 2] > 230))
    )
    mid_ok = np.mean(
        ((mid_slice[:, :, 0] > 215) & (mid_slice[:, :, 1] > 180) & (mid_slice[:, :, 2] < 95))
        | ((mid_slice[:, :, 0] > 230) & (mid_slice[:, :, 1] > 230) & (mid_slice[:, :, 2] > 230))
    )
    bot_ok = np.mean(
        ((bot_slice[:, :, 0] > 225) & (bot_slice[:, :, 1] > 65) & (bot_slice[:, :, 1] < 155) & (bot_slice[:, :, 2] < 80))
        | ((bot_slice[:, :, 0] > 230) & (bot_slice[:, :, 1] > 230) & (bot_slice[:, :, 2] > 230))
    )

    is_power_bar = bool((top_ok > 0.65) and (mid_ok > 0.65) and (bot_ok > 0.65) and not is_pullup)
    slider_pos = None

    if is_power_bar:
        bar_col = arr[int(0.168 * h):int(0.728 * h), int(0.485 * w):int(0.515 * w)]
        white_rows = np.mean(bar_col > 232, axis=(1, 2)) > 0.75
        if np.any(white_rows):
            wy = np.where(white_rows)[0]
            slider_pos = float(np.mean(wy) / max(1, bar_col.shape[0]))

    # -----------------------------------------------------------------
    # 4. DETECÇÃO DA FAIXA LARANJA DE CHEGADA
    # -----------------------------------------------------------------
    small = arr[::2, ::2]
    sh, sw, _ = small.shape
    R = small[:, :, 0].astype(np.int16)
    G = small[:, :, 1].astype(np.int16)
    B = small[:, :, 2].astype(np.int16)

    orange_tiles = (R > 220) & (G > 115) & (G < 230) & (B < 95) & ((R - B) > 130) & (R >= G - 5)
    glow_strip = (R > 245) & (G > 205) & (G < 252) & (B > 110) & (B < 235) & (R >= G) & (G > B + 15)

    combined = orange_tiles | glow_strip

    roi = np.zeros_like(combined, dtype=bool)
    roi[int(0.42 * sh):int(0.95 * sh), int(0.16 * sw):int(0.84 * sw)] = True
    roi[int(0.72 * sh):, :int(0.25 * sw)] = False
    roi[int(0.83 * sh):, int(0.32 * sw):int(0.68 * sw)] = False
    roi[int(0.43 * sh):int(0.79 * sh), int(0.36 * sw):int(0.51 * sw)] = False

    det_all = combined & roi
    det_orange = orange_tiles & roi

    foot_roi = np.zeros_like(combined, dtype=bool)
    foot_roi[int(0.68 * sh):int(0.94 * sh), int(0.20 * sw):int(0.80 * sw)] = True
    foot_roi[int(0.83 * sh):, int(0.32 * sw):int(0.68 * sw)] = False
    det_feet = orange_tiles & foot_roi

    scale_factor = (1024 * 576) / float(sw * sh)
    orange_total = int(np.sum(det_all) * scale_factor)
    orange_pure = int(np.sum(det_orange) * scale_factor)
    orange_feet = int(np.sum(det_feet) * scale_factor)

    if np.any(det_all):
        ys, xs = np.where(det_all)
        mx = float(np.mean(xs) / sw)
        my = float(np.mean(ys) / sh)
    else:
        mx, my = 0.5, 0.5

    return {
        "is_pullup": is_pullup,
        "x2_pos": x2_pos,
        "is_power_bar": is_power_bar,
        "slider_pos": slider_pos,
        "orange_total": orange_total,
        "orange_pure": orange_pure,
        "orange_feet": orange_feet,
        "orange_mx": mx,
        "orange_my": my,
    }


# =====================================================================
# INTERFACE GRÁFICA E LÓGICA DO BOT
# =====================================================================
class RobloxThrowBotApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Bot Roblox v2 - Faixa Laranja + Arremesso +20 + Skip + Barra 2X")
        self.root.geometry("580x740")
        self.root.attributes("-topmost", True)

        self.running = False
        self.recording_walk = False
        self.walk_record_start = 0.0
        self.active_keys = set()
        self.hwnd = 0
        self.throw_count = 0
        self.x2_click_count = 0
        self.state = "PARADO"

        # Configurações padrão otimizadas
        self.config = {
            "mode": "hybrid",             # "focus", "background", "hybrid"
            "turn_dir": "right",          # "right" (Seta ->) ou "left" (Seta <-)
            "slider_threshold": 0.17,     # 0.00 a 0.22 = zona do +20 no topo da barra
            "max_walk_time": 9.5,         # Tempo máximo andando até a faixa laranja (seg)
            "use_fixed_walk_time": False, # Desmarcado por padrão para andar até a barra abrir!
            "recorded_walk_time": 4.0,    # Tempo padrão caso marque tempo fixo
            "post_throw_wait": 4.5,       # Tempo clicando em TAP TO SKIP e aguardando voltar ao cercado
            "auto_skip": True,            # Clicar automaticamente no TAP TO SKIP após arremessar
            "auto_pullup_x2": True,       # Clicar automaticamente na bolinha roxa x2 durante a barra
        }
        self.load_config()
        # Se o usuário tinha gravado 0.5s sem querer antes, corrige para um valor seguro
        if float(self.config.get("recorded_walk_time", 4.0)) < 1.2:
            self.config["recorded_walk_time"] = 4.0
            self.config["use_fixed_walk_time"] = False

        self.build_ui()
        self.setup_hotkeys()

        self.worker_thread = threading.Thread(target=self.bot_loop, daemon=True)
        self.worker_thread.start()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.config.update(data)
            except Exception:
                pass

    def save_config(self):
        self.config["mode"] = self.mode_var.get()
        self.config["turn_dir"] = self.turn_dir_var.get()
        self.config["slider_threshold"] = float(self.thresh_var.get())
        self.config["use_fixed_walk_time"] = bool(self.use_fixed_var.get())
        self.config["recorded_walk_time"] = float(self.walk_time_var.get())
        self.config["post_throw_wait"] = float(self.wait_time_var.get())
        self.config["auto_skip"] = bool(self.auto_skip_var.get())
        self.config["auto_pullup_x2"] = bool(self.auto_x2_var.get())
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    def build_ui(self):
        pad = {"padx": 10, "pady": 4}

        # Cabeçalho de Status
        status_frame = ttk.LabelFrame(self.root, text="Status em Tempo Real")
        status_frame.pack(fill="x", **pad)

        self.lbl_state = ttk.Label(
            status_frame, text="ESTADO: PARADO (Pressione F8 para Iniciar/Pausar)", font=("Segoe UI", 11, "bold"), foreground="#d9534f"
        )
        self.lbl_state.pack(anchor="w", padx=8, pady=3)

        self.lbl_vision = ttk.Label(
            status_frame, text="Janela Roblox: Procurando... | Barra +20: Não | Faixa Laranja: 0 px", font=("Segoe UI", 9)
        )
        self.lbl_vision.pack(anchor="w", padx=8, pady=2)

        self.lbl_throws = ttk.Label(
            status_frame, text="Arremessos (+20): 0  |  Cliques Bônus Barra (x2): 0", font=("Segoe UI", 9, "bold"), foreground="#0275d8"
        )
        self.lbl_throws.pack(anchor="w", padx=8, pady=2)

        # Preview da Visão do Bot
        preview_frame = ttk.LabelFrame(self.root, text="Visão do Bot (Captura da Janela do Roblox)")
        preview_frame.pack(fill="x", **pad)
        self.lbl_preview = ttk.Label(preview_frame, text="Abra o Roblox para visualizar a captura aqui")
        self.lbl_preview.pack(padx=5, pady=4)

        # Extras Automáticos (Tap to Skip & Barra 2X)
        extra_frame = ttk.LabelFrame(self.root, text="Automações Extras (Tap to Skip & Barra 2X)")
        extra_frame.pack(fill="x", **pad)

        self.auto_x2_var = tk.BooleanVar(value=self.config.get("auto_pullup_x2", True))
        ttk.Checkbutton(
            extra_frame,
            text="💪 Auto-Click no Círculo Roxo 'x2' (Dedo Amarelo) enquanto estiver fazendo barra",
            variable=self.auto_x2_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        self.auto_skip_var = tk.BooleanVar(value=self.config.get("auto_skip", True))
        ttk.Checkbutton(
            extra_frame,
            text="⏩ Auto-Click em 'TAP TO SKIP' quando pegar algum animal no final do arremesso",
            variable=self.auto_skip_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        # Modo de Operação (Alt+Tab / Segundo Plano)
        mode_frame = ttk.LabelFrame(self.root, text="Modo de Execução (Alt+Tab / Segundo Plano)")
        mode_frame.pack(fill="x", **pad)

        self.mode_var = tk.StringVar(value=self.config["mode"])
        ttk.Radiobutton(
            mode_frame,
            text="Híbrido Recomendado (Monitora no Alt+Tab e foca rápido para andar/clicar sem falha)",
            variable=self.mode_var,
            value="hybrid",
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)
        ttk.Radiobutton(
            mode_frame,
            text="Segundo Plano Puro (Envia teclas via Win32 sem sair do Alt+Tab - deixe o Roblox aberto atrás)",
            variable=self.mode_var,
            value="background",
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)
        ttk.Radiobutton(
            mode_frame,
            text="Janela Focada (100% DirectInput com o Roblox aberto na tela)",
            variable=self.mode_var,
            value="focus",
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        # Configurações de Busca e Caminhada
        nav_frame = ttk.LabelFrame(self.root, text="Navegação até a Faixa Laranja")
        nav_frame.pack(fill="x", **pad)

        row1 = ttk.Frame(nav_frame)
        row1.pack(fill="x", padx=8, pady=2)
        ttk.Label(row1, text="Direção para girar a câmera quando NÃO vê a faixa laranja:").pack(side="left")
        self.turn_dir_var = tk.StringVar(value=self.config["turn_dir"])
        ttk.Radiobutton(row1, text="Direita (→)", variable=self.turn_dir_var, value="right", command=self.save_config).pack(side="left", padx=5)
        ttk.Radiobutton(row1, text="Esquerda (←)", variable=self.turn_dir_var, value="left", command=self.save_config).pack(side="left", padx=5)

        self.use_fixed_var = tk.BooleanVar(value=self.config["use_fixed_walk_time"])
        ttk.Checkbutton(
            nav_frame,
            text="Limitar caminhada por tempo fixo (Desmarcado = anda até a barra 'TAP TO THROW!' abrir)",
            variable=self.use_fixed_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        row2 = ttk.Frame(nav_frame)
        row2.pack(fill="x", padx=8, pady=3)
        ttk.Label(row2, text="Tempo fixo (segundos):").pack(side="left")
        self.walk_time_var = tk.DoubleVar(value=self.config["recorded_walk_time"])
        ttk.Entry(row2, textvariable=self.walk_time_var, width=7).pack(side="left", padx=5)

        self.btn_record = ttk.Button(row2, text="⏱ Gravar Tempo Andando (F9)", command=self.toggle_record_walk)
        self.btn_record.pack(side="left", padx=5)

        # Configurações do Arremesso (+20)
        throw_frame = ttk.LabelFrame(self.root, text="Calibragem do Arremesso (+20) e Skip")
        throw_frame.pack(fill="x", **pad)

        row3 = ttk.Frame(throw_frame)
        row3.pack(fill="x", padx=8, pady=2)
        ttk.Label(row3, text="Zona do Topo (+20) [0.05 = topo extremo | 0.17 = +20 seguro]:").pack(side="left")
        self.thresh_var = tk.DoubleVar(value=self.config["slider_threshold"])
        ttk.Spinbox(row3, from_=0.04, to=0.30, increment=0.01, textvariable=self.thresh_var, width=6, command=self.save_config).pack(side="left", padx=5)

        row4 = ttk.Frame(throw_frame)
        row4.pack(fill="x", padx=8, pady=2)
        ttk.Label(row4, text="Duração do arremesso / cliques em TAP TO SKIP (s):").pack(side="left")
        self.wait_time_var = tk.DoubleVar(value=self.config["post_throw_wait"])
        ttk.Spinbox(row4, from_=2.0, to=15.0, increment=0.5, textvariable=self.wait_time_var, width=6, command=self.save_config).pack(side="left", padx=5)

        # Botão Principal
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=8)

        self.btn_toggle = tk.Button(
            btn_frame,
            text="▶ INICIAR BOT (F8)",
            bg="#28a745",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            height=2,
            command=self.toggle_bot,
        )
        self.btn_toggle.pack(fill="x")

    def setup_hotkeys(self):
        try:
            keyboard.add_hotkey("f8", lambda: self.root.after(0, self.toggle_bot))
            keyboard.add_hotkey("f9", lambda: self.root.after(0, self.toggle_record_walk))
        except Exception:
            pass

    def toggle_record_walk(self):
        if not self.recording_walk:
            self.recording_walk = True
            self.walk_record_start = time.time()
            self.btn_record.config(text="⏹ Parar Gravação (F9)")
        else:
            self.recording_walk = False
            elapsed = round(max(1.0, time.time() - self.walk_record_start), 2)
            self.walk_time_var.set(elapsed)
            self.use_fixed_var.set(True)
            self.save_config()
            self.btn_record.config(text="⏱ Gravar Tempo Andando (F9)")

    def toggle_bot(self):
        self.save_config()
        self.running = not self.running
        if self.running:
            self.state = "BUSCANDO_FAIXA"
            self.btn_toggle.config(text="⏸ PAUSAR BOT (F8)", bg="#dc3545")
            self.lbl_state.config(text="ESTADO: RODANDO - Verificando Tela", foreground="#28a745")
        else:
            self.release_all_keys()
            self.state = "PARADO"
            self.btn_toggle.config(text="▶ INICIAR BOT (F8)", bg="#28a745")
            self.lbl_state.config(text="ESTADO: PARADO (Pressione F8 para Iniciar)", foreground="#d9534f")

    # =====================================================================
    # CONTROLE DE TECLAS (COM PULSOS DE ROTAÇÃO SUAVES)
    # =====================================================================
    def set_key(self, key_name: str, down: bool):
        mode = self.config["mode"]
        if down and key_name not in self.active_keys:
            self.active_keys.add(key_name)
            if mode == "background":
                send_background_key(self.hwnd, key_name, True)
            else:
                self.ensure_roblox_focus_if_needed()
                send_direct_key(key_name, True)
        elif not down and key_name in self.active_keys:
            self.active_keys.discard(key_name)
            if mode == "background":
                send_background_key(self.hwnd, key_name, False)
            else:
                send_direct_key(key_name, False)
                send_background_key(self.hwnd, key_name, False)

    def pulse_turn_key(self, key_name: str, duration: float = 0.055):
        """
        Gira a câmera em pequenos passos controlados e solta imediatamente!
        Isso evita 100% que a tecla de seta fique presa e faça o personagem girar sem parar.
        """
        mode = self.config["mode"]
        if mode == "background":
            send_background_key(self.hwnd, key_name, True)
            time.sleep(duration)
            send_background_key(self.hwnd, key_name, False)
        else:
            self.ensure_roblox_focus_if_needed()
            send_direct_key(key_name, True)
            time.sleep(duration)
            send_direct_key(key_name, False)

    def release_all_keys(self):
        for k in ("w", "a", "s", "d", "left", "right", "space"):
            try:
                send_direct_key(k, False)
                if self.hwnd:
                    send_background_key(self.hwnd, k, False)
            except Exception:
                pass
        self.active_keys.clear()

    def ensure_roblox_focus_if_needed(self):
        if self.config["mode"] in ("focus", "hybrid") and self.hwnd:
            fg = win32gui.GetForegroundWindow()
            if fg != self.hwnd and fg != self.root.winfo_id():
                try:
                    ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
                    win32gui.SetForegroundWindow(self.hwnd)
                    ctypes.windll.user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
                except Exception:
                    pass

    # =====================================================================
    # LOOP PRINCIPAL DE VISÃO E MÁQUINA DE ESTADOS
    # =====================================================================
    def bot_loop(self):
        sct = mss.mss()
        last_preview_time = 0.0
        state_start_time = time.time()
        walk_start_time = 0.0
        last_skip_click = 0.0
        last_x2_click = 0.0

        while True:
            loop_start = time.time()

            if not self.hwnd or not win32gui.IsWindow(self.hwnd):
                self.hwnd = find_roblox_hwnd()

            arr = capture_window_rgb(self.hwnd, sct) if self.hwnd else None

            if arr is None:
                self.release_all_keys()
                self.update_ui_status("Janela do Roblox não encontrada ou minimizada!", None)
                time.sleep(0.3)
                continue

            info = analyze_frame(arr)

            if loop_start - last_preview_time > 0.25:
                last_preview_time = loop_start
                self.update_ui_status(None, info, arr)

            if not self.running:
                time.sleep(0.05)
                continue

            # =================================================================
            # 1) MODO TREINO DE BARRA (PULL-UPS) OU CÍRCULO ROXO "x2" NA TELA
            # Se o botão vermelho STOP estiver na tela (fazendo barra) ou o círculo
            # roxo com a mão amarela (x2) aparecer, não anda e clica no círculo x2!
            # =================================================================
            if info["is_pullup"] or info["x2_pos"] is not None:
                self.release_all_keys()
                self.state = "TREINANDO_BARRA_2X"
                if self.config.get("auto_pullup_x2", True) and info["x2_pos"] is not None:
                    if time.time() - last_x2_click >= 0.12:
                        nx, ny = info["x2_pos"]
                        click_at_normalized_pos(
                            self.hwnd,
                            nx,
                            ny,
                            self.config["mode"],
                            restore_window=(self.config["mode"] == "hybrid"),
                            also_press_space=False,
                        )
                        self.x2_click_count += 1
                        last_x2_click = time.time()
                time.sleep(0.03)
                continue
            elif self.state == "TREINANDO_BARRA_2X":
                # Saiu da barra -> volta a buscar a faixa laranja
                self.state = "BUSCANDO_FAIXA"
                state_start_time = time.time()

            # =================================================================
            # 2) BARRA VERTICAL DE ARREMESSO ("TAP TO THROW!") NA TELA
            # =================================================================
            if info["is_power_bar"]:
                if self.state != "ARREMESSANDO_+20":
                    self.release_all_keys()
                    self.state = "ARREMESSANDO_+20"
                    state_start_time = time.time()

                slider_pos = info["slider_pos"]
                thresh = float(self.config["slider_threshold"])

                # Clica exatamente quando a barrinha branca atinge o topo (+20)
                if slider_pos is not None and slider_pos <= thresh:
                    click_at_normalized_pos(
                        self.hwnd,
                        0.50,
                        0.55,
                        self.config["mode"],
                        restore_window=(self.config["mode"] == "hybrid"),
                        also_press_space=True,
                    )
                    self.throw_count += 1
                    self.state = "TAP_TO_SKIP_E_RETORNO"
                    state_start_time = time.time()
                    last_skip_click = time.time()
                    time.sleep(0.20)
                continue

            # =================================================================
            # 3) APÓS O ARREMESSO: CLICA EM "TAP TO SKIP" E AGUARDA VOLTAR AO CERCADO
            # =================================================================
            if self.state == "TAP_TO_SKIP_E_RETORNO":
                self.release_all_keys()
                elapsed_wait = time.time() - state_start_time

                # Durante o voo / captura do animal, clica a cada 0.45s para dar "TAP TO SKIP"
                if self.config.get("auto_skip", True) and elapsed_wait > 0.6:
                    if time.time() - last_skip_click >= 0.45:
                        click_at_normalized_pos(
                            self.hwnd,
                            0.50,
                            0.62,
                            self.config["mode"],
                            restore_window=(self.config["mode"] == "hybrid"),
                            also_press_space=False,
                        )
                        last_skip_click = time.time()

                # Quando terminar o tempo de retorno ao cercado, inicia novo ciclo
                if elapsed_wait >= float(self.config["post_throw_wait"]):
                    self.state = "BUSCANDO_FAIXA"
                    state_start_time = time.time()
                time.sleep(0.05)
                continue

            # =================================================================
            # 4) BUSCANDO A FAIXA LARANJA (SEM GIRAR EM CÍRCULOS!)
            # Se a faixa laranja já está visível (ex: 27511 px, X=0.53 como no seu print),
            # NÃO gira a câmera e vai direto para ANDANDO_ATE_FAIXA!
            # =================================================================
            if self.state == "BUSCANDO_FAIXA":
                self.set_key("w", False)

                # Se já enxerga a faixa laranja (qualquer quantidade >= 2000 px centralizada
                # ou >= 8000 px quando já está de frente para ela como em 27511 px):
                is_aligned = (info["orange_total"] >= 2000 and 0.25 <= info["orange_mx"] <= 0.78)
                is_already_in_front = (info["orange_total"] >= 8000 and 0.18 <= info["orange_mx"] <= 0.82)

                if is_aligned or is_already_in_front:
                    self.release_all_keys()
                    self.state = "ANDANDO_ATE_FAIXA"
                    walk_start_time = time.time()
                    state_start_time = time.time()
                    continue

                # Caso ainda esteja olhando para a parede após o teleporte, dá 1 pulso curto na câmera
                turn_key = "right" if self.config["turn_dir"] == "right" else "left"
                # Se a faixa já começou a aparecer num canto da tela, gira na direção dela
                if info["orange_total"] >= 1000:
                    turn_key = "right" if info["orange_mx"] > 0.5 else "left"

                self.pulse_turn_key(turn_key, duration=0.055)
                time.sleep(0.035)
                continue

            # =================================================================
            # 5) ANDANDO RETO ATÉ A FAIXA LARANJA (ATÉ A BARRA +20 APARECER)
            # =================================================================
            if self.state == "ANDANDO_ATE_FAIXA":
                elapsed_walk = time.time() - walk_start_time

                # Só usa tempo fixo se o usuário marcou explicitamente a caixa
                if self.config["use_fixed_walk_time"] and elapsed_walk >= float(self.config["recorded_walk_time"]):
                    self.release_all_keys()
                    self.state = "AGUARDANDO_BARRA"
                    state_start_time = time.time()
                    continue

                # Timeout de segurança caso o personagem trave em alguma cerca (9.5s)
                if elapsed_walk > float(self.config["max_walk_time"]):
                    self.release_all_keys()
                    self.state = "BUSCANDO_FAIXA"
                    state_start_time = time.time()
                    continue

                # Se por algum motivo virou para a parede e perdeu totalmente a faixa (< 300 px) no início:
                if info["orange_total"] < 300 and elapsed_walk > 0.6 and info["orange_feet"] < 500:
                    self.release_all_keys()
                    self.state = "BUSCANDO_FAIXA"
                    state_start_time = time.time()
                    continue

                # Anda reto para frente com W (sem apertar setas enquanto anda para nunca rodar em círculos!)
                self.set_key("w", True)
                time.sleep(0.025)
                continue

            # =================================================================
            # 6) AGUARDANDO A BARRA DE ARREMESSO ABRIR (CASO USE TEMPO FIXO)
            # =================================================================
            if self.state == "AGUARDANDO_BARRA":
                self.release_all_keys()
                if time.time() - state_start_time > 1.2:
                    # Se parou um pouco antes da faixa, anda mais 0.6s para frente
                    self.set_key("w", True)
                    time.sleep(0.6)
                    self.release_all_keys()
                    state_start_time = time.time()
                time.sleep(0.02)
                continue

    def update_ui_status(self, err_msg, info, arr=None):
        def _upd():
            if err_msg:
                self.lbl_vision.config(text=err_msg)
                return
            if info:
                bar_txt = (
                    f"SIM (pos={info['slider_pos']:.2f})"
                    if info["is_power_bar"] and info["slider_pos"] is not None
                    else ("SIM" if info["is_power_bar"] else "Não")
                )
                x2_txt = "SIM!" if info["x2_pos"] is not None else ("Barra Ativa" if info["is_pullup"] else "Não")
                self.lbl_vision.config(
                    text=f"Barra +20: {bar_txt} | Treino 2X: {x2_txt} | Faixa Laranja: {info['orange_total']} px (X={info['orange_mx']:.2f})"
                )
                self.lbl_throws.config(
                    text=f"Arremessos (+20): {self.throw_count}  |  Cliques Bônus Barra (x2): {self.x2_click_count}"
                )
                if self.running:
                    self.lbl_state.config(text=f"ESTADO: {self.state} (F8 para Pausar)", foreground="#28a745")
            if arr is not None:
                try:
                    pil_img = Image.fromarray(arr).resize((360, 202), Image.Resampling.NEAREST)
                    tk_img = ImageTk.PhotoImage(pil_img)
                    self.lbl_preview.config(image=tk_img, text="")
                    self.lbl_preview.image = tk_img
                except Exception:
                    pass

        self.root.after(0, _upd)


if __name__ == "__main__":
    root = tk.Tk()
    app = RobloxThrowBotApp(root)
    root.mainloop()
