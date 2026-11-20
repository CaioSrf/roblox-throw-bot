# -*- coding: utf-8 -*-
"""
Bot Automático para Roblox v6 - Análise Completa do Mapa (3 Estágios) + Guardar Mob + Arremesso (+20) + Skip + Barra 2X
=======================================================================================================================
Inovações de Eficiência e Navegação da v6:
1. Análise Completa do Mapa em 3 Estágios (Multi-Landmark Vision):
   - ESTÁGIO 1 (Longa Distância / Saindo do Cercado):
     Quando o personagem está longe da faixa laranja (onde a faixa tem menos de 1000 px), o bot localiza o
     "Farol de Longa Distância": o Letreiro Magenta "EVENT" + a Tenda Roxa do Mago + o Corredor Aberto de
     Grama Verde (> 20.000 px de grama livre, garantindo que não há parede ou cerca bloqueando).
     Ele mira ligeiramente à direita da Tenda do Mago (+0.12 no eixo X, que é exatamente onde a faixa laranja fica!)
     e já começa a andar imediatamente de longe!
   - ESTÁGIO 2 (Média Distância / Aproximação):
     Assim que a linha brilhante e os blocos laranjas passam de 1.200 px, o bot transfere a mira do Mago para o
     centro exato da Faixa Laranja (mantendo X ≈ 0.53).
   - ESTÁGIO 3 (Curta Distância / Chegada em ~27.511 px, X=0.53):
     Ao atingir alta densidade de pixels laranjas (> 15.000 px) e pisar na faixa, aguarda/abre a barra "TAP TO THROW!".

2. Correção de Rota sem Parar de Andar (Proportional Strafe A/D + Micro-Camera Steering):
   - Enquanto segura `W` continuamente, se o alvo (`target_x`) desviar de `X = 0.53`, o bot dá micro-toques
     proporcionais de `A` / `D` (ou `Seta ←` / `Seta →`) sem soltar o `W`! O personagem faz uma curva suave
     e contínua em velocidade máxima até o ponto exato da faixa laranja.

3. Radar Anti-Colisão / Destravamento Automático (Optical Flow / Stuck Detector):
   - Se o bot estiver segurando `W`, mas a imagem do mapa não mudar (preso em quina de cerca ou poste),
     ele detecta a colisão em 1.2s e faz uma manobra automática de contorno (pulo `Espaço` + passo lateral `D`/`A`).

4. Retirada Automática Instantânea do Mob Novo da Mão (Tecla Numérica do Slot + Clique na Hotbar):
   - Quando volta do arremesso com 100% de chance de ter um mob novo na mão (borda branca na hotbar),
     o bot identifica qual slot está equipado, aperta o atalho numérico (`1`..`0`) E clica no slot para
     guardar o mob em menos de 150ms, limpando a tela para a leitura do mapa!

5. Predição de Velocidade da Barra +20 (Velocity Lead Compensation):
   - Calcula a velocidade com que a barrinha branca está subindo para acionar o clique milissegundos antes
     do topo, compensando o tempo de resposta do jogo e cravando `+20` todas as vezes.
"""

import ctypes
import json
import os
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import keyboard
import mss
import numpy as np
from PIL import Image, ImageTk
import win32api
import win32con
import win32gui
import win32ui

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_bot.json")

# =====================================================================
# SIMULAÇÃO DE INPUT (DIRECTINPUT SCAN CODES)
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
    "1": (0x31, 0x02, False),
    "2": (0x32, 0x03, False),
    "3": (0x33, 0x04, False),
    "4": (0x34, 0x05, False),
    "5": (0x35, 0x06, False),
    "6": (0x36, 0x07, False),
    "7": (0x37, 0x08, False),
    "8": (0x38, 0x09, False),
    "9": (0x39, 0x0A, False),
    "0": (0x30, 0x0B, False),
    "left": (win32con.VK_LEFT, 0x4B, True),
    "right": (win32con.VK_RIGHT, 0x4D, True),
    "up": (win32con.VK_UP, 0x48, True),
    "down": (win32con.VK_DOWN, 0x50, True),
}


def focus_roblox_window(hwnd: int):
    if not hwnd or not win32gui.IsWindow(hwnd):
        return
    fg = win32gui.GetForegroundWindow()
    if fg != hwnd:
        try:
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            win32gui.SetForegroundWindow(hwnd)
            ctypes.windll.user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.012)
        except Exception:
            pass


def send_direct_key(key_name: str, down: bool):
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


def click_roblox_pos(hwnd: int, norm_x: float, norm_y: float, restore_cursor: bool = True, also_press_space: bool = False):
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

    prev_pos = win32api.GetCursorPos()
    focus_roblox_window(hwnd)

    win32api.SetCursorPos((screen_x, screen_y))
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.mi = MouseInput(1, 1, 0, MOUSEEVENTF_MOVE, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(0), ii_)
    SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    time.sleep(0.01)

    ii_.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(0), ii_)
    SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    if also_press_space:
        send_direct_key("space", True)

    time.sleep(0.022)

    ii_.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(0), ii_)
    SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    if also_press_space:
        send_direct_key("space", False)

    if restore_cursor:
        try:
            time.sleep(0.008)
            win32api.SetCursorPos(prev_pos)
        except Exception:
            pass


# =====================================================================
# CAPTURA DE TELA DA JANELA DO ROBLOX
# =====================================================================
def find_roblox_hwnd() -> int:
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
# VISÃO COMPUTACIONAL v6: ANÁLISE COMPLETA DO MAPA EM 3 ESTÁGIOS
# =====================================================================
def detect_equipped_hotbar_slot(arr: np.ndarray):
    """
    Detecta se há algum mob equipado na mão verificando a borda branca brilhante
    em qualquer um dos slots da hotbar inferior (1 a 0).
    Também estima a tecla numérica ('1'..'9','0') correspondente para desequipar via teclado + clique!
    """
    h, w, _ = arr.shape
    x0, x1 = int(0.25 * w), int(0.75 * w)

    top_band = arr[int(0.860 * h):int(0.900 * h), x0:x1]
    mid_band = arr[int(0.910 * h):int(0.942 * h), x0:x1]
    bot_band = arr[int(0.946 * h):int(0.958 * h), x0:x1]

    has_white_top = np.any((top_band[:, :, 0] > 215) & (top_band[:, :, 1] > 215) & (top_band[:, :, 2] > 210), axis=0)
    has_white_bot = np.any((bot_band[:, :, 0] > 215) & (bot_band[:, :, 1] > 215) & (bot_band[:, :, 2] > 210), axis=0)
    has_dark_mid = np.mean(mid_band, axis=(0, 2)) < 115

    equipped_cols = has_white_top & has_white_bot & has_dark_mid
    win = max(10, int(0.035 * w))
    best_score = 0.0
    best_cx = None

    for i in range(max(1, len(equipped_cols) - win)):
        score = float(np.sum(equipped_cols[i:i + win])) / float(win)
        if score > best_score:
            best_score = score
            best_cx = (x0 + i + win // 2) / float(w)

    if best_score > 0.55 and best_cx is not None:
        # Se está próximo de x=0.30 (primeiro slot da esquerda, onde todo mob novo entra!), é a tecla '1'
        slot_key = "1" if best_cx < 0.335 else None
        return True, float(best_cx), 0.915, slot_key
    return False, None, 0.915, None


def analyze_frame(arr: np.ndarray):
    h, w, _ = arr.shape

    # 1. DETECÇÃO DO TREINO DE BARRA (Botão vermelho "STOP")
    stop_box = arr[int(0.79 * h):int(0.875 * h), int(0.435 * w):int(0.565 * w)]
    red_ratio = np.mean((stop_box[:, :, 0] > 190) & (stop_box[:, :, 1] < 50) & (stop_box[:, :, 2] < 50))
    is_pullup = bool(red_ratio > 0.22)

    # 2. DETECÇÃO DO CÍRCULO ROXO "x2" COM DEDO AMARELO
    x2_pos = None
    roi_y0, roi_y1 = int(0.10 * h), int(0.82 * h)
    roi_x0, roi_x1 = int(0.15 * w), int(0.85 * w)
    sub = arr[roi_y0:roi_y1:2, roi_x0:roi_x1:2]
    sR = sub[:, :, 0].astype(np.int16)
    sG = sub[:, :, 1].astype(np.int16)
    sB = sub[:, :, 2].astype(np.int16)

    purple_mask = (sR > 160) & (sR < 250) & (sG > 45) & (sG < 180) & (sB > 205) & ((sB - sG) > 65) & ((sR - sG) > 45)
    yellow_hand = (sR > 235) & (sG > 185) & (sG < 242) & (sB > 55) & (sB < 170) & ((sR - sB) > 80)

    scale_sub = (512 * 288) / float(max(1, sub.shape[0] * sub.shape[1]))
    if np.sum(purple_mask) * scale_sub > 80 and np.sum(yellow_hand) * scale_sub > 15:
        hy, hx = np.where(yellow_hand)
        cy_sub = int(np.median(hy))
        cx_sub = int(np.median(hx))
        rad = max(12, int(0.06 * sub.shape[1]))
        y_min, y_max = max(0, cy_sub - rad), min(sub.shape[0], cy_sub + rad)
        x_min, x_max = max(0, cx_sub - rad), min(sub.shape[1], cx_sub + rad)
        local_purple = np.sum(purple_mask[y_min:y_max, x_min:x_max]) * scale_sub
        if local_purple > 95:
            norm_x = (roi_x0 + cx_sub * 2) / float(w)
            norm_y = (roi_y0 + cy_sub * 2) / float(h)
            x2_pos = (float(norm_x), float(norm_y))

    # 3. VERIFICAÇÃO RIGOROSA DA BARRA DE ARREMESSO ("TAP TO THROW!")
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

    # 4. DETECÇÃO DE MOB EQUIPADO NA MÃO (Hotbar com borda branca selecionada)
    mob_equipped, mob_slot_x, mob_slot_y, mob_slot_key = detect_equipped_hotbar_slot(arr)
    if is_pullup or is_power_bar:
        mob_equipped = False

    # 5. ANÁLISE COMPLETA DO MAPA EM 3 ESTÁGIOS (Farol EVENT/Mago + Corredor Verde + Faixa Laranja)
    small = arr[::2, ::2]
    sh, sw, _ = small.shape
    R = small[:, :, 0].astype(np.int16)
    G = small[:, :, 1].astype(np.int16)
    B = small[:, :, 2].astype(np.int16)

    ui_mask = np.ones((sh, sw), dtype=bool)
    ui_mask[:, :int(0.16 * sw)] = False
    ui_mask[:, int(0.84 * sw):] = False
    ui_mask[int(0.72 * sh):, :int(0.25 * sw)] = False
    ui_mask[int(0.83 * sh):, int(0.24 * sw):int(0.76 * sw)] = False
    ui_mask[int(0.43 * sh):int(0.79 * sh), int(0.36 * sw):int(0.51 * sw)] = False

    # A) Faixa Laranja + Linha Brilhante no Chão (y > 0.41*sh)
    floor_roi = ui_mask.copy()
    floor_roi[:int(0.41 * sh), :] = False

    orange_tiles = (R > 220) & (G > 115) & (G < 230) & (B < 95) & ((R - B) > 130) & (R >= G - 5) & floor_roi
    glow_strip = (R > 245) & (G > 205) & (G < 252) & (B > 110) & (B < 235) & (R >= G) & (G > B + 15) & floor_roi
    finish_line = orange_tiles | glow_strip

    foot_roi = ui_mask.copy()
    foot_roi[:int(0.68 * sh), :] = False
    foot_roi[int(0.94 * sh):, :] = False
    det_feet = orange_tiles & foot_roi

    # B) Farol de Longa Distância: Letreiro Magenta "EVENT" + Tenda Roxa do Mago (y entre 0.04*sh e 0.65*sh)
    horizon_roi = ui_mask.copy()
    horizon_roi[:int(0.04 * sh), :] = False
    horizon_roi[int(0.65 * sh):, :] = False

    magenta_event = (R > 205) & (G < 70) & (B > 175) & ((R - G) > 140) & ((B - G) > 110) & horizon_roi
    purple_booth = (R > 80) & (R < 170) & (G > 25) & (G < 110) & (B > 185) & ((B - G) > 90) & ((B - R) > 30) & horizon_roi

    # C) Corredor Aberto de Grama Verde à Frente (y de 0.45*sh a 0.82*sh, x de 0.25*sw a 0.75*sw)
    corridor_roi = ui_mask.copy()
    corridor_roi[:int(0.45 * sh), :] = False
    corridor_roi[int(0.82 * sh):, :] = False
    corridor_roi[:, :int(0.25 * sw)] = False
    corridor_roi[:, int(0.75 * sw):] = False
    green_grass = (G > 200) & (R < 145) & (B < 75) & ((G - R) > 75) & corridor_roi

    scale_factor = (1024 * 576) / float(sw * sh)
    orange_total = int(np.sum(finish_line) * scale_factor)
    orange_pure = int(np.sum(orange_tiles) * scale_factor)
    orange_feet = int(np.sum(det_feet) * scale_factor)
    event_px = int(np.sum(magenta_event) * scale_factor)
    booth_px = int(np.sum(purple_booth) * scale_factor)
    grass_px = int(np.sum(green_grass) * scale_factor)

    # Decisão de Estágio de Navegação no Mapa:
    nav_stage = "SEARCHING"
    target_x = 0.53
    orange_mx = 0.53

    if np.any(finish_line):
        ys, xs = np.where(finish_line)
        orange_mx = float(np.mean(xs) / sw)

    if orange_total >= 1200:
        target_x = orange_mx
        nav_stage = "ESTAGIO_3_CHEGADA" if orange_total >= 15000 else "ESTAGIO_2_FAIXA_VISIVEL"
    elif (
        (event_px >= 180 and booth_px >= 400 and grass_px >= 20000)
        or (event_px >= 400 and grass_px >= 20000)
        or (booth_px >= 1800 and orange_total >= 400 and grass_px >= 25000)
    ):
        # Vê o Farol (EVENT + Tenda do Mago + Corredor de Grama Verde) lá de longe!
        ys, xs = np.where(magenta_event | purple_booth)
        beacon_x = float(np.mean(xs) / sw)
        # A faixa laranja fica imediatamente à direita da tenda do mago (+0.12)
        target_x = min(0.78, beacon_x + 0.12)
        nav_stage = "ESTAGIO_1_FAROL_LONGE"

    # Assinatura visual rápida do frame (para o detector de colisão / stuck)
    frame_sig = small[::4, ::4].astype(np.float32)

    return {
        "is_pullup": is_pullup,
        "x2_pos": x2_pos,
        "is_power_bar": is_power_bar,
        "slider_pos": slider_pos,
        "mob_equipped": mob_equipped,
        "mob_slot_x": mob_slot_x,
        "mob_slot_y": mob_slot_y,
        "mob_slot_key": mob_slot_key,
        "nav_stage": nav_stage,
        "target_x": target_x,
        "orange_total": orange_total,
        "orange_pure": orange_pure,
        "orange_feet": orange_feet,
        "orange_mx": orange_mx,
        "event_px": event_px,
        "booth_px": booth_px,
        "grass_px": grass_px,
        "frame_sig": frame_sig,
    }


# =====================================================================
# INTERFACE GRÁFICA E LÓGICA DO BOT (v6)
# =====================================================================
class RobloxThrowBotApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Bot Roblox v6 - Mapa 3 Estágios + Guardar Mob + Arremesso +20 + Skip + Barra 2X")
        self.root.geometry("630x800")
        self.root.attributes("-topmost", True)

        self.running = False
        self.recording_walk = False
        self.walk_record_start = 0.0
        self.active_keys = set()
        self.hwnd = 0
        self.throw_count = 0
        self.x2_click_count = 0
        self.unequip_count = 0
        self.state = "PARADO"

        self.config = {
            "restore_cursor": True,
            "turn_dir": "right",
            "slider_threshold": 0.18,
            "max_walk_time": 14.0,
            "use_fixed_walk_time": False,
            "recorded_walk_time": 4.0,
            "post_throw_wait": 4.5,
            "auto_skip": True,
            "auto_pullup_x2": True,
            "auto_unequip_mob": True,
        }
        self.load_config()
        self.config["auto_pullup_x2"] = True
        self.config["auto_skip"] = True
        self.config["auto_unequip_mob"] = True
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
        self.config["restore_cursor"] = bool(self.restore_cursor_var.get())
        self.config["turn_dir"] = self.turn_dir_var.get()
        self.config["slider_threshold"] = float(self.thresh_var.get())
        self.config["use_fixed_walk_time"] = bool(self.use_fixed_var.get())
        self.config["recorded_walk_time"] = float(self.walk_time_var.get())
        self.config["post_throw_wait"] = float(self.wait_time_var.get())
        self.config["auto_skip"] = bool(self.auto_skip_var.get())
        self.config["auto_pullup_x2"] = bool(self.auto_x2_var.get())
        self.config["auto_unequip_mob"] = bool(self.auto_unequip_var.get())
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    def launch_isolated_setup(self):
        bat_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "1_CONFIGURAR_SESSAO_ISOLADA_ADMIN.bat")
        if os.path.exists(bat_path):
            subprocess.Popen(["cmd.exe", "/c", "start", "", bat_path], shell=True)
        else:
            messagebox.showerror("Erro", f"Arquivo não encontrado:\n{bat_path}")

    def build_ui(self):
        pad = {"padx": 10, "pady": 4}

        status_frame = ttk.LabelFrame(self.root, text="Radar do Mapa e Status em Tempo Real (v6)")
        status_frame.pack(fill="x", **pad)

        self.lbl_state = ttk.Label(
            status_frame, text="ESTADO: PARADO (Pressione F8 para Iniciar/Pausar)", font=("Segoe UI", 11, "bold"), foreground="#d9534f"
        )
        self.lbl_state.pack(anchor="w", padx=8, pady=3)

        self.lbl_vision = ttk.Label(
            status_frame, text="Radar: Aguardando... | Faixa: 0 px | Farol EVENT: 0 px | Grama Livre: 0 px", font=("Segoe UI", 9)
        )
        self.lbl_vision.pack(anchor="w", padx=8, pady=2)

        self.lbl_throws = ttk.Label(
            status_frame,
            text="Arremessos (+20): 0  |  Mobs Guardados: 0  |  Cliques Barra (x2): 0",
            font=("Segoe UI", 9, "bold"),
            foreground="#0275d8",
        )
        self.lbl_throws.pack(anchor="w", padx=8, pady=2)

        preview_frame = ttk.LabelFrame(self.root, text="Visão do Bot (Captura da Janela do Roblox)")
        preview_frame.pack(fill="x", **pad)
        self.lbl_preview = ttk.Label(preview_frame, text="Abra o Roblox para visualizar a captura aqui")
        self.lbl_preview.pack(padx=5, pady=4)

        extra_frame = ttk.LabelFrame(self.root, text="Automações Inteligentes Ativas")
        extra_frame.pack(fill="x", **pad)

        self.auto_unequip_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            extra_frame,
            text="🐾 Auto-Guardar Mob Novo da Mão (Tecla do Slot + Clique na Hotbar p/ liberar visão do mapa)",
            variable=self.auto_unequip_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        self.auto_x2_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            extra_frame,
            text="💪 Auto-Click no Círculo Roxo 'x2' (Dedo Amarelo) durante o treino de barra",
            variable=self.auto_x2_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        self.auto_skip_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            extra_frame,
            text="⏩ Auto-Click em 'TAP TO SKIP' ao capturar animal no final do arremesso",
            variable=self.auto_skip_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        mode_frame = ttk.LabelFrame(self.root, text="Controle de Mouse e Sessão Isolada (RDP / Windows Sandbox)")
        mode_frame.pack(fill="x", **pad)

        self.restore_cursor_var = tk.BooleanVar(value=self.config.get("restore_cursor", True))
        ttk.Checkbutton(
            mode_frame,
            text="⚡ Devolver meu cursor imediatamente para onde estava após clicar (Clique de 22ms)",
            variable=self.restore_cursor_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        btn_rdp = ttk.Button(
            mode_frame,
            text="🖥️ Configurar Sessão Isolada (RDP Local / Windows Sandbox) para rodar 100% em Background",
            command=self.launch_isolated_setup,
        )
        btn_rdp.pack(fill="x", padx=8, pady=4)

        nav_frame = ttk.LabelFrame(self.root, text="Navegação 3 Estágios (Farol EVENT/Mago -> Faixa Laranja 27.511 px)")
        nav_frame.pack(fill="x", **pad)

        row1 = ttk.Frame(nav_frame)
        row1.pack(fill="x", padx=8, pady=2)
        ttk.Label(row1, text="Direção para escanear o mapa ao sair do cercado:").pack(side="left")
        self.turn_dir_var = tk.StringVar(value=self.config["turn_dir"])
        ttk.Radiobutton(row1, text="Direita (→)", variable=self.turn_dir_var, value="right", command=self.save_config).pack(side="left", padx=5)
        ttk.Radiobutton(row1, text="Esquerda (←)", variable=self.turn_dir_var, value="left", command=self.save_config).pack(side="left", padx=5)

        self.use_fixed_var = tk.BooleanVar(value=self.config["use_fixed_walk_time"])
        ttk.Checkbutton(
            nav_frame,
            text="Limitar caminhada por tempo fixo (Desmarcado = navega pelo mapa até a barra 'TAP TO THROW!' abrir)",
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

        throw_frame = ttk.LabelFrame(self.root, text="Calibragem do Arremesso (+20 com Predição de Velocidade)")
        throw_frame.pack(fill="x", **pad)

        row3 = ttk.Frame(throw_frame)
        row3.pack(fill="x", padx=8, pady=2)
        ttk.Label(row3, text="Zona do Topo (+20) [0.05 = topo extremo | 0.18 = +20 calibrado]:").pack(side="left")
        self.thresh_var = tk.DoubleVar(value=self.config["slider_threshold"])
        ttk.Spinbox(row3, from_=0.04, to=0.30, increment=0.01, textvariable=self.thresh_var, width=6, command=self.save_config).pack(side="left", padx=5)

        row4 = ttk.Frame(throw_frame)
        row4.pack(fill="x", padx=8, pady=2)
        ttk.Label(row4, text="Duração do arremesso / cliques em TAP TO SKIP (s):").pack(side="left")
        self.wait_time_var = tk.DoubleVar(value=self.config["post_throw_wait"])
        ttk.Spinbox(row4, from_=2.0, to=15.0, increment=0.5, textvariable=self.wait_time_var, width=6, command=self.save_config).pack(side="left", padx=5)

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
            self.state = "BUSCANDO_ROTA_NO_MAPA"
            self.btn_toggle.config(text="⏸ PAUSAR BOT (F8)", bg="#dc3545")
            self.lbl_state.config(text="ESTADO: RODANDO - Escaneando Mapa", foreground="#28a745")
            if self.hwnd:
                focus_roblox_window(self.hwnd)
        else:
            self.release_all_keys()
            self.state = "PARADO"
            self.btn_toggle.config(text="▶ INICIAR BOT (F8)", bg="#28a745")
            self.lbl_state.config(text="ESTADO: PARADO (Pressione F8 para Iniciar)", foreground="#d9534f")

    def start_walking_forward(self):
        if self.hwnd:
            focus_roblox_window(self.hwnd)
        if "w" not in self.active_keys:
            self.active_keys.add("w")
        send_direct_key("w", True)

    def steer_while_walking(self, target_x: float):
        """
        Mantém W pressionado e faz micro-ajustes laterais com A/D (strafe) e setas
        para cravar a rota exatamente em X = 0.53 (o ponto da faixa laranja de 27.511 px)
        sem jamais parar de andar!
        """
        error = target_x - 0.53
        if abs(error) <= 0.11:
            return
        # Micro-pulso proporcional ao erro horizontal (15ms a 35ms)
        pulse_dur = min(0.038, max(0.014, abs(error) * 0.08))
        steer_key = "d" if error > 0 else "a"
        send_direct_key(steer_key, True)
        time.sleep(pulse_dur)
        send_direct_key(steer_key, False)

    def unstick_maneuver(self):
        """Manobra rápida de desvio caso o personagem encoste numa cerca ou poste."""
        if self.hwnd:
            focus_roblox_window(self.hwnd)
        send_direct_key("space", True)
        send_direct_key("d", True)
        time.sleep(0.22)
        send_direct_key("space", False)
        send_direct_key("d", False)

    def pulse_turn_key(self, key_name: str, duration: float = 0.06):
        if self.hwnd:
            focus_roblox_window(self.hwnd)
        send_direct_key(key_name, True)
        time.sleep(duration)
        send_direct_key(key_name, False)

    def release_all_keys(self):
        for k in ("w", "a", "s", "d", "left", "right", "space"):
            try:
                send_direct_key(k, False)
            except Exception:
                pass
        self.active_keys.clear()

    def bot_loop(self):
        sct = mss.mss()
        last_preview_time = 0.0
        state_start_time = time.time()
        walk_start_time = 0.0
        last_w_refresh = 0.0
        last_steer_time = 0.0
        last_skip_click = 0.0
        last_x2_click = 0.0
        last_unequip_time = 0.0
        prev_slider_pos = None
        prev_frame_sig = None
        last_sig_check_time = 0.0

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

            # Destrava imediatamente se a barra de arremesso fechou
            if self.state == "ARREMESSANDO_+20" and not info["is_power_bar"]:
                self.release_all_keys()
                self.state = "BUSCANDO_ROTA_NO_MAPA"
                state_start_time = time.time()
                prev_slider_pos = None

            # =================================================================
            # 1) MODO TREINO DE BARRA (PULL-UPS) OU CÍRCULO ROXO "x2" NA TELA
            # =================================================================
            if info["is_pullup"] or info["x2_pos"] is not None:
                self.release_all_keys()
                self.state = "TREINANDO_BARRA_2X"
                if self.config.get("auto_pullup_x2", True) and info["x2_pos"] is not None:
                    if time.time() - last_x2_click >= 0.11:
                        nx, ny = info["x2_pos"]
                        click_roblox_pos(
                            self.hwnd,
                            nx,
                            ny,
                            restore_cursor=self.config.get("restore_cursor", True),
                            also_press_space=False,
                        )
                        self.x2_click_count += 1
                        last_x2_click = time.time()
                time.sleep(0.02)
                continue
            elif self.state == "TREINANDO_BARRA_2X":
                self.state = "BUSCANDO_ROTA_NO_MAPA"
                state_start_time = time.time()

            # =================================================================
            # 2) BARRA VERTICAL DE ARREMESSO ("TAP TO THROW!") COM PREDIÇÃO DE VELOCIDADE
            # =================================================================
            if info["is_power_bar"]:
                if self.state != "ARREMESSANDO_+20":
                    self.release_all_keys()
                    self.state = "ARREMESSANDO_+20"
                    state_start_time = time.time()
                    prev_slider_pos = None

                slider_pos = info["slider_pos"]
                thresh = float(self.config["slider_threshold"])

                if slider_pos is not None:
                    # Predição de velocidade: se a barrinha branca está subindo rápido em direção ao +20,
                    # antecipa o clique em 0.04 para compensar o tempo do clique e cravar no topo!
                    effective_pos = slider_pos
                    if prev_slider_pos is not None and slider_pos < prev_slider_pos:
                        vel_up = prev_slider_pos - slider_pos
                        effective_pos = max(0.0, slider_pos - vel_up * 0.65)
                    prev_slider_pos = slider_pos

                    if effective_pos <= thresh:
                        click_roblox_pos(
                            self.hwnd,
                            0.50,
                            0.55,
                            restore_cursor=self.config.get("restore_cursor", True),
                            also_press_space=True,
                        )
                        self.throw_count += 1
                        self.state = "TAP_TO_SKIP_E_RETORNO"
                        state_start_time = time.time()
                        last_skip_click = time.time()
                        prev_slider_pos = None
                        time.sleep(0.20)
                continue

            # =================================================================
            # 3) APÓS O ARREMESSO: CLICA EM "TAP TO SKIP" E AGUARDA VOLTAR AO CERCADO
            # =================================================================
            if self.state == "TAP_TO_SKIP_E_RETORNO":
                self.release_all_keys()
                elapsed_wait = time.time() - state_start_time

                if self.config.get("auto_skip", True) and elapsed_wait > 0.55:
                    if time.time() - last_skip_click >= 0.42:
                        click_roblox_pos(
                            self.hwnd,
                            0.50,
                            0.62,
                            restore_cursor=self.config.get("restore_cursor", True),
                            also_press_space=False,
                        )
                        last_skip_click = time.time()

                if elapsed_wait >= float(self.config["post_throw_wait"]):
                    self.state = "BUSCANDO_ROTA_NO_MAPA"
                    state_start_time = time.time()
                time.sleep(0.04)
                continue

            # =================================================================
            # 4) GUARDAR MOB EQUIPADO NA MÃO ANTES DE ESCANEAR O MAPA!
            # Aperta a tecla do slot (ex: '1') E clica no slot da hotbar para garantir
            # que o mob saia da mão imediatamente e não bloqueie os pixels do mapa.
            # =================================================================
            if self.config.get("auto_unequip_mob", True) and info["mob_equipped"] and info["mob_slot_x"] is not None:
                if time.time() - last_unequip_time >= 0.40:
                    self.release_all_keys()
                    self.state = "GUARDANDO_MOB_DA_MAO"
                    focus_roblox_window(self.hwnd)
                    if info["mob_slot_key"] is not None:
                        send_direct_key(info["mob_slot_key"], True)
                        time.sleep(0.03)
                        send_direct_key(info["mob_slot_key"], False)
                    else:
                        click_roblox_pos(
                            self.hwnd,
                            info["mob_slot_x"],
                            info["mob_slot_y"],
                            restore_cursor=self.config.get("restore_cursor", True),
                            also_press_space=False,
                        )
                    self.unequip_count += 1
                    last_unequip_time = time.time()
                    time.sleep(0.22)
                    self.state = "BUSCANDO_ROTA_NO_MAPA"
                    continue

            # =================================================================
            # 5) NAVEGAÇÃO NO MAPA EM 3 ESTÁGIOS (FAROL LONGE -> MÉDIA -> FAIXA 27.511 PX)
            # Assim que QUALQUER um dos 3 estágios é detectado (mesmo lá de longe no cercado!),
            # o bot já começa a andar para frente imediatamente!
            # =================================================================
            if info["nav_stage"] != "SEARCHING":
                if not self.state.startswith("NAVEGANDO_"):
                    walk_start_time = time.time()
                    last_sig_check_time = time.time()
                    prev_frame_sig = info["frame_sig"]
                    self.start_walking_forward()
                    last_w_refresh = time.time()

                self.state = f"NAVEGANDO_{info['nav_stage']}"
                elapsed_walk = time.time() - walk_start_time

                # Verifica limite de tempo fixo se o usuário marcou a caixa
                if self.config["use_fixed_walk_time"] and elapsed_walk >= float(self.config["recorded_walk_time"]):
                    self.release_all_keys()
                    self.state = "AGUARDANDO_BARRA"
                    state_start_time = time.time()
                    continue

                # Mantém W pressionado continuamente
                if "w" not in self.active_keys or (time.time() - last_w_refresh > 0.30):
                    self.start_walking_forward()
                    last_w_refresh = time.time()

                # Ajusta a rota suavemente com A/D em direção a X = 0.53 sem parar o W!
                if time.time() - last_steer_time > 0.14:
                    self.steer_while_walking(info["target_x"])
                    last_steer_time = time.time()

                # Radar Anti-Colisão (Optical Flow): verifica a cada 1.1s se o personagem ficou preso numa cerca
                if time.time() - last_sig_check_time > 1.1:
                    if prev_frame_sig is not None:
                        diff = float(np.mean(np.abs(info["frame_sig"] - prev_frame_sig)))
                        if diff < 3.2:
                            # Imagem quase não mudou enquanto segurava W -> contorna obstáculo!
                            self.unstick_maneuver()
                            self.start_walking_forward()
                    prev_frame_sig = info["frame_sig"]
                    last_sig_check_time = time.time()

                time.sleep(0.02)
                continue

            # =================================================================
            # 6) ESCANEANDO O MAPA (QUANDO ESTÁ OLHANDO PARA A PAREDE DO CERCADO)
            # =================================================================
            self.release_all_keys()
            self.state = "BUSCANDO_ROTA_NO_MAPA"
            turn_key = "right" if self.config["turn_dir"] == "right" else "left"
            self.pulse_turn_key(turn_key, duration=0.065)
            time.sleep(0.03)

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
                mob_txt = "SIM" if info["mob_equipped"] else "Não"
                self.lbl_vision.config(
                    text=(
                        f"Estágio: {info['nav_stage']} | Alvo X={info['target_x']:.2f} | "
                        f"Faixa: {info['orange_total']} px | Farol EVENT/Mago: {info['event_px'] + info['booth_px']} px | "
                        f"Mob Mão: {mob_txt} | Barra: {bar_txt}"
                    )
                )
                self.lbl_throws.config(
                    text=f"Arremessos (+20): {self.throw_count}  |  Mobs Guardados: {self.unequip_count}  |  Cliques Barra (x2): {self.x2_click_count}"
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
