# -*- coding: utf-8 -*-
"""
Bot Automático para Roblox v8 - Refatoração Arquitetural Completa
=================================================================
Melhorias obrigatórias e correções aplicadas na v8:
1. Navegação com Travamento de Alinhamento + Setas (left/right):
   - Substituído A/D por pulsos proporcionais nas setas `left` / `right` para girar a câmera e alinhar `target_x` com `0.52`.
   - Trava de alinhamento: só segura `W` quando `abs(target_x - 0.52) <= 0.14`. Se desalinhado, solta `W`, alinha primeiro e depois anda.
2. Hotbar Dinâmica do Roblox:
   - Detecta dinamicamente todos os slots visíveis na hotbar inferior da esquerda para a direita.
   - Mapeia o slot equipado com borda branca para a tecla correta (`1`..`0`) e usa clique em `(best_cx, 0.915)` como fallback se continuar equipado no frame seguinte.
3. Radar Anti-Colisão Preciso (`frame_sig` + `unstick_maneuver`):
   - `frame_sig` recortado exclusivamente para a faixa lateral inferior do chão (`small[int(0.55*sh):int(0.85*sh):4, int(0.05*sw):int(0.28*sw):4]`).
   - `unstick_maneuver(attempt)` alterna `a` (pares) e `d` (ímpares), recua com `s` (`0.15s`), pula (`space` + lado por `0.25s`) e retoma `w`.
4. Latência e Precisão no Arremesso (+20):
   - Removido `also_press_space=True` no clique do arremesso.
   - Verificação de direção da barrinha branca: se `slider_pos > prev_slider_pos` (descendo), ignora o clique e aguarda subir novamente.
   - Durante `is_power_bar == True`, suspende o envio de `arr` para `update_ui_status` para maximizar o FPS do loop.
5. Persistência Real do `config_bot.json`:
   - Respeita integralmente as opções salvas pelo usuário ao iniciar.
6. Auto-Fechar "Sell Animals" + Detecção Espacial Precisa do Círculo Roxo `x2`:
   - Fecha automaticamente a janela "Sell Animals" (além de Animal Index e Throw Power) e afasta-se da barraca se necessário.
   - Localiza o círculo roxo `x2` pela maior concentração local de roxo + mão amarela interna, funcionando em qualquer ponto aleatório da tela.
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
# TABELA OFICIAL DE MUNDOS / FASES E THROW POWER (ANIMAL INDEX)
# =====================================================================
WORLD_PHASES = [
    {"name": "MAX (Maior Fase Atual)", "power": 999999, "slider_x": 0.3600, "completed_default": False},
    {"name": "1. Forest (TP: 16)", "power": 16, "slider_x": 0.0735, "completed_default": False},
    {"name": "2. Savanna (TP: 176)", "power": 176, "slider_x": 0.0803, "completed_default": False},
    {"name": "3. Desert (TP: 333)", "power": 333, "slider_x": 0.0875, "completed_default": False},
    {"name": "4. Jungle (TP: 513)", "power": 513, "slider_x": 0.0955, "completed_default": False},
    {"name": "5. Ocean (TP: 716)", "power": 716, "slider_x": 0.1025, "completed_default": False},
    {"name": "6. Mountains (TP: 884)", "power": 884, "slider_x": 0.1095, "completed_default": False},
    {"name": "7. Taiga (TP: 1099)", "power": 1099, "slider_x": 0.1185, "completed_default": False},
    {"name": "8. Winter (TP: 1350)", "power": 1350, "slider_x": 0.1275, "completed_default": False},
    {"name": "9. Prehistoric Forest (100%)", "power": 1650, "slider_x": 0.1370, "completed_default": True},
    {"name": "10. Deep Waters (100%)", "power": 2050, "slider_x": 0.1540, "completed_default": True},
    {"name": "11. Hell", "power": 2600, "slider_x": 0.1630, "completed_default": False},
    {"name": "12. Ancient Ruins", "power": 3300, "slider_x": 0.1760, "completed_default": False},
    {"name": "13. Mythical Paradise (100%)", "power": 4100, "slider_x": 0.1940, "completed_default": True},
    {"name": "14. Shadow Realm", "power": 5000, "slider_x": 0.2050, "completed_default": False},
    {"name": "15. Harvest Fields", "power": 5900, "slider_x": 0.2500, "completed_default": False},
    {"name": "16. Phantom Harbor", "power": 6300, "slider_x": 0.2970, "completed_default": False},
    {"name": "17. Nuclear Wasteland", "power": 6728, "slider_x": 0.3438, "completed_default": False},
]

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
    "e": (0x45, 0x12, False),
    "space": (0x20, 0x39, False),
    "backspace": (0x08, 0x0E, False),
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


def tap_key(key_name: str, duration: float = 0.035):
    send_direct_key(key_name, True)
    time.sleep(duration)
    send_direct_key(key_name, False)


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


def drag_slider_to_pos(hwnd: int, target_norm_x: float, restore_cursor: bool = True):
    if not hwnd or not win32gui.IsWindow(hwnd):
        return
    focus_roblox_window(hwnd)
    click_roblox_pos(hwnd, 0.195, 0.858, restore_cursor=False, also_press_space=False)
    time.sleep(0.25)
    click_roblox_pos(hwnd, target_norm_x, 0.710, restore_cursor=False, also_press_space=False)
    time.sleep(0.18)
    click_roblox_pos(hwnd, 0.357, 0.630, restore_cursor=restore_cursor, also_press_space=False)
    time.sleep(0.15)


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
# VISÃO COMPUTACIONAL v8
# =====================================================================
def detect_equipped_hotbar_slot(arr: np.ndarray):
    """
    Detecta dinamicamente a hotbar inferior centralizada (de 1 até 10 itens).
    Conta os blocos visíveis da esquerda para a direita para mapear o slot equipado
    exatamente para a tecla numérica ('1'..'9','0') correspondente, priorizando '1' quando há poucos itens.
    Retorna (is_equipped, slot_center_x, slot_center_y, slot_key_str).
    """
    h, w, _ = arr.shape
    x0, x1 = int(0.24 * w), int(0.76 * w)

    top_band = arr[int(0.860 * h):int(0.900 * h), x0:x1]
    mid_band = arr[int(0.908 * h):int(0.942 * h), x0:x1]
    bot_band = arr[int(0.946 * h):int(0.958 * h), x0:x1]

    has_white_top = np.any((top_band[:, :, 0] > 215) & (top_band[:, :, 1] > 215) & (top_band[:, :, 2] > 210), axis=0)
    has_white_bot = np.any((bot_band[:, :, 0] > 215) & (bot_band[:, :, 1] > 215) & (bot_band[:, :, 2] > 210), axis=0)
    has_dark_mid = np.mean(mid_band, axis=(0, 2)) < 115

    equipped_cols = has_white_top & has_white_bot & has_dark_mid
    win = max(10, int(0.034 * w))
    best_score = 0.0
    best_cx = None

    for i in range(max(1, len(equipped_cols) - win)):
        score = float(np.sum(equipped_cols[i:i + win])) / float(win)
        if score > best_score:
            best_score = score
            best_cx = (x0 + i + win // 2) / float(w)

    if best_score > 0.52 and best_cx is not None:
        # Mapeia dinamicamente os slots visíveis pela presença de fundo escuro da hotbar
        slot_mask = np.mean(mid_band, axis=(0, 2)) < 120
        # Encontra intervalos contínuos que representam cada quadrado da hotbar
        diff = np.diff(slot_mask.astype(np.int8), prepend=0, append=0)
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]

        min_slot_w = max(12, int(0.028 * w))
        visible_centers = []
        for s, e in zip(starts, ends):
            if (e - s) >= min_slot_w:
                seg_w = (e - s) / float(w)
                n_sub = max(1, int(round(seg_w / 0.044)))
                sub_w = (e - s) / float(n_sub)
                for k in range(n_sub):
                    cx_norm = (x0 + s + (k + 0.5) * sub_w) / float(w)
                    visible_centers.append(cx_norm)

        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
        if len(visible_centers) <= 2:
            slot_key = "1"
        elif visible_centers:
            # Usa o centro do primeiro slot válido como âncora e divide pelo passo de 0.044*w
            first_cx = visible_centers[0]
            idx = int(round((best_cx - first_cx) / 0.044))
            idx = max(0, min(9, idx))
            slot_key = keys[idx]
        else:
            slot_key = "1"

        return True, float(best_cx), 0.915, slot_key

    return False, None, 0.915, None


def detect_open_modals(arr: np.ndarray):
    """
    Detecta janelas abertas que bloqueiam o bot:
    - SELL_ANIMALS (Cabeçalho vermelho, fundo escuro, botão X vermelho em (0.754, 0.142))
    - ANIMAL_INDEX (Cabeçalho rosa/roxo, botão X vermelho em (0.812, 0.209))
    - THROW_POWER_POPUP (Fundo escuro à esquerda, botão X vermelho em (0.357, 0.630))
    """
    h, w, _ = arr.shape

    # 1. SELL ANIMALS (ex: media_1795147122499_48d2854d.jpg)
    sell_hdr = arr[int(0.10 * h):int(0.175 * h), int(0.25 * w):int(0.75 * w)]
    sell_body = arr[int(0.25 * h):int(0.84 * h), int(0.25 * w):int(0.75 * w)]
    sell_x_box = arr[int(0.115 * h):int(0.170 * h), int(0.730 * w):int(0.780 * w)]
    is_sell_hdr = np.mean((sell_hdr[:, :, 0] > 200) & (sell_hdr[:, :, 1] < 65) & (sell_hdr[:, :, 2] < 65)) > 0.25
    is_sell_body = np.mean(np.max(sell_body, axis=2) < 50) > 0.55
    is_sell_x = np.mean((sell_x_box[:, :, 0] > 195) & (sell_x_box[:, :, 1] < 65) & (sell_x_box[:, :, 2] < 65)) > 0.20
    if is_sell_hdr and is_sell_body and is_sell_x:
        return "SELL_ANIMALS", (0.754, 0.142)

    # 2. ANIMAL INDEX
    idx_x_box = arr[int(0.185 * h):int(0.230 * h), int(0.790 * w):int(0.830 * w)]
    idx_hdr = arr[int(0.175 * h):int(0.225 * h), int(0.38 * w):int(0.62 * w)]
    is_idx_x = np.mean((idx_x_box[:, :, 0] > 195) & (idx_x_box[:, :, 1] < 65) & (idx_x_box[:, :, 2] < 65)) > 0.25
    is_idx_pink = np.mean((idx_hdr[:, :, 0] > 180) & (idx_hdr[:, :, 2] > 180)) > 0.35
    if is_idx_x and is_idx_pink:
        return "ANIMAL_INDEX", (0.812, 0.209)

    # 3. THROW POWER POPUP
    tp_x_box = arr[int(0.600 * h):int(0.665 * h), int(0.335 * w):int(0.380 * w)]
    tp_bg = arr[int(0.66 * h):int(0.78 * h), int(0.08 * w):int(0.32 * w)]
    is_tp_x = np.mean((tp_x_box[:, :, 0] > 195) & (tp_x_box[:, :, 1] < 60) & (tp_x_box[:, :, 2] < 60)) > 0.12
    is_tp_dark = np.mean(tp_bg) < 60
    if is_tp_x and is_tp_dark:
        return "THROW_POWER_POPUP", (0.357, 0.630)

    return None, None


def detect_x2_circle(arr: np.ndarray):
    """
    Identifica o círculo roxo 'x2' com a mãozinha amarela em qualquer posição aleatória
    do meio da tela pela concentração local de pixels roxos + pixels amarelos internos.
    """
    h, w, _ = arr.shape
    roi_y0, roi_y1 = int(0.10 * h), int(0.82 * h)
    roi_x0, roi_x1 = int(0.15 * w), int(0.85 * w)
    sub = arr[roi_y0:roi_y1:2, roi_x0:roi_x1:2]
    sR = sub[:, :, 0].astype(np.int16)
    sG = sub[:, :, 1].astype(np.int16)
    sB = sub[:, :, 2].astype(np.int16)

    purple_mask = (sR > 160) & (sR < 250) & (sG > 45) & (sG < 180) & (sB > 205) & ((sB - sG) > 65) & ((sR - sG) > 45)
    yellow_hand = (sR > 235) & (sG > 185) & (sG < 242) & (sB > 55) & (sB < 170) & ((sR - sB) > 80)

    scale_sub = (512 * 288) / float(max(1, sub.shape[0] * sub.shape[1]))
    if np.sum(purple_mask) * scale_sub < 80 or np.sum(yellow_hand) * scale_sub < 15:
        return None

    # Divide a área de busca em uma grade 8x6 para encontrar o cluster local mais denso de roxo+amarelo,
    # evitando desvios caso haja texto amarelo em outro canto da tela
    sh, sw = sub.shape[:2]
    grid_r, grid_c = 6, 8
    cell_h, cell_w = max(1, sh // grid_r), max(1, sw // grid_c)

    best_score = 0.0
    best_cell = None
    for r in range(grid_r):
        for c in range(grid_c):
            y0, y1 = max(0, r * cell_h - 10), min(sh, (r + 1) * cell_h + 10)
            x0, x1 = max(0, c * cell_w - 10), min(sw, (c + 1) * cell_w + 10)
            p_cnt = float(np.sum(purple_mask[y0:y1, x0:x1])) * scale_sub
            y_cnt = float(np.sum(yellow_hand[y0:y1, x0:x1])) * scale_sub
            if p_cnt >= 95 and y_cnt >= 14:
                score = p_cnt + y_cnt * 2.0
                if score > best_score:
                    best_score = score
                    best_cell = (y0, y1, x0, x1)

    if best_cell is None:
        return None

    y0, y1, x0, x1 = best_cell
    hy, hx = np.where(yellow_hand[y0:y1, x0:x1])
    cy_sub = y0 + int(np.median(hy))
    cx_sub = x0 + int(np.median(hx))

    norm_x = (roi_x0 + cx_sub * 2) / float(w)
    norm_y = (roi_y0 + cy_sub * 2) / float(h)
    return (float(norm_x), float(norm_y))


def analyze_frame(arr: np.ndarray):
    h, w, _ = arr.shape

    # 0. VERIFICA MODAIS ABERTOS (Sell Animals / Animal Index / Throw Power Popup)
    modal_name, modal_close_pos = detect_open_modals(arr)

    # 1. DETECÇÃO DO TREINO DE BARRA (Botão vermelho "STOP")
    stop_box = arr[int(0.79 * h):int(0.875 * h), int(0.435 * w):int(0.565 * w)]
    red_ratio = np.mean((stop_box[:, :, 0] > 190) & (stop_box[:, :, 1] < 50) & (stop_box[:, :, 2] < 50))
    is_pullup = bool(red_ratio > 0.22 and modal_name is None)

    # 2. DETECÇÃO DO CÍRCULO ROXO "x2" COM DEDO AMARELO EM POSIÇÃO ALEATÓRIA (APENAS DURANTE TREINO DE BARRA)
    x2_pos = detect_x2_circle(arr) if (is_pullup and modal_name is None) else None

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

    is_power_bar = bool((top_ok > 0.65) and (mid_ok > 0.65) and (bot_ok > 0.65) and not is_pullup and modal_name is None)
    slider_pos = None

    if is_power_bar:
        bar_col = arr[int(0.168 * h):int(0.728 * h), int(0.485 * w):int(0.515 * w)]
        white_rows = np.mean(bar_col > 232, axis=(1, 2)) > 0.75
        if np.any(white_rows):
            wy = np.where(white_rows)[0]
            slider_pos = float(np.mean(wy) / max(1, bar_col.shape[0]))

    # 4. DETECÇÃO DE MOB EQUIPADO NA MÃO (Hotbar Dinâmica)
    mob_equipped, mob_slot_x, mob_slot_y, mob_slot_key = detect_equipped_hotbar_slot(arr)
    if is_pullup or is_power_bar or modal_name is not None:
        mob_equipped = False

    # 5. ANÁLISE COMPLETA DO MAPA RESISTENTE A TELA POLUÍDA / MOBS GIGANTES
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

    floor_roi = ui_mask.copy()
    floor_roi[:int(0.40 * sh), :] = False

    orange_tiles = (R > 220) & (G > 115) & (G < 230) & (B < 95) & ((R - B) > 130) & (R >= G - 5) & floor_roi
    glow_strip = (R > 245) & (G > 205) & (G < 252) & (B > 110) & (B < 235) & (R >= G) & (G > B + 15) & floor_roi
    finish_line = orange_tiles | glow_strip

    foot_roi = ui_mask.copy()
    foot_roi[:int(0.68 * sh), :] = False
    foot_roi[int(0.94 * sh):, :] = False
    det_feet = orange_tiles & foot_roi

    horizon_roi = ui_mask.copy()
    horizon_roi[:int(0.04 * sh), :] = False
    horizon_roi[int(0.65 * sh):, :] = False

    magenta_event = (R > 205) & (G < 70) & (B > 175) & ((R - G) > 140) & ((B - G) > 110) & horizon_roi
    purple_booth = (R > 80) & (R < 170) & (G > 25) & (G < 110) & (B > 185) & ((B - G) > 90) & ((B - R) > 30) & horizon_roi
    sell_booth = (R > 210) & (G > 40) & (G < 95) & (B > 40) & (B < 95) & ((R - G) > 135) & (np.abs(G - B) < 20) & horizon_roi

    yellow_pad = (R > 235) & (G > 195) & (G < 238) & (B < 40) & ((R - B) > 205) & floor_roi

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
    sell_px = int(np.sum(sell_booth) * scale_factor)
    yellow_pad_px = int(np.sum(yellow_pad) * scale_factor)
    grass_px = int(np.sum(green_grass) * scale_factor)

    is_screen_cluttered = bool(grass_px < 9000 and orange_total < 1500 and not is_pullup and not is_power_bar)

    upgrade_pad_x = None
    if yellow_pad_px >= 350:
        ys, xs = np.where(yellow_pad)
        upgrade_pad_x = float(np.mean(xs) / sw)

    nav_stage = "SEARCHING"
    target_x = 0.52
    orange_mx = 0.52

    if np.any(finish_line):
        ys, xs = np.where(finish_line)
        orange_mx = float(np.mean(xs) / sw)

    if orange_total >= 1200:
        target_x = orange_mx
        nav_stage = "ESTAGIO_3_CHEGADA" if orange_total >= 15000 else "ESTAGIO_2_FAIXA_VISIVEL"
    elif (
        (event_px >= 180 and booth_px >= 400 and grass_px >= 14000)
        or (event_px >= 400 and grass_px >= 14000)
        or (booth_px >= 1800 and orange_total >= 350 and grass_px >= 16000)
        or (sell_px >= 380 and orange_total >= 250)
    ):
        beacon_mask = magenta_event | purple_booth | sell_booth
        ys, xs = np.where(beacon_mask)
        beacon_x = float(np.mean(xs) / sw)
        target_x = min(0.78, beacon_x + (0.04 if sell_px >= 380 else 0.12))
        nav_stage = "ESTAGIO_1_FAROL_LONGE"

    # Assinatura visual recortada exclusivamente para a faixa lateral inferior do chão
    # (ignora nuvens no céu e animação idle do avatar para o detector de colisão!)
    frame_sig = small[int(0.55 * sh):int(0.85 * sh):4, int(0.05 * sw):int(0.28 * sw):4].astype(np.float32)

    return {
        "modal_name": modal_name,
        "modal_close_pos": modal_close_pos,
        "is_pullup": is_pullup,
        "x2_pos": x2_pos,
        "is_power_bar": is_power_bar,
        "slider_pos": slider_pos,
        "mob_equipped": mob_equipped,
        "mob_slot_x": mob_slot_x,
        "mob_slot_y": mob_slot_y,
        "mob_slot_key": mob_slot_key,
        "is_screen_cluttered": is_screen_cluttered,
        "yellow_pad_px": yellow_pad_px,
        "upgrade_pad_x": upgrade_pad_x,
        "nav_stage": nav_stage,
        "target_x": target_x,
        "orange_total": orange_total,
        "orange_pure": orange_pure,
        "orange_feet": orange_feet,
        "orange_mx": orange_mx,
        "event_px": event_px,
        "booth_px": booth_px,
        "sell_px": sell_px,
        "grass_px": grass_px,
        "frame_sig": frame_sig,
    }


# =====================================================================
# INTERFACE GRÁFICA E LÓGICA DO BOT (v8)
# =====================================================================
class RobloxThrowBotApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Bot Roblox v8 - Auto-Index + Auto-Upgrade (E) + Barra 2X + Arremesso +20")
        self.root.geometry("650x840")
        self.root.attributes("-topmost", True)

        self.running = False
        self.active_keys = set()
        self.hwnd = 0
        self.throw_count = 0
        self.x2_click_count = 0
        self.unequip_count = 0
        self.upgrade_attempts = 0
        self.current_phase_idx = 0
        self.throws_in_current_phase = 0
        self.needs_power_apply = False
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
            "auto_upgrade_e": True,
            "target_phase_name": WORLD_PHASES[0]["name"],
            "auto_rotate_phases": False,
            "throws_per_phase": 15,
        }
        self.load_config()

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
        self.config["auto_upgrade_e"] = bool(self.auto_upgrade_var.get())
        self.config["target_phase_name"] = self.phase_combo.get()
        self.config["auto_rotate_phases"] = bool(self.auto_rotate_var.get())
        self.config["throws_per_phase"] = int(self.throws_per_phase_var.get())
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    def trigger_apply_phase_now(self):
        self.save_config()
        self.needs_power_apply = True

    def launch_isolated_setup(self):
        bat_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "1_CONFIGURAR_SESSAO_ISOLADA_ADMIN.bat")
        if os.path.exists(bat_path):
            subprocess.Popen(["cmd.exe", "/c", "start", "", bat_path], shell=True)
        else:
            messagebox.showerror("Erro", f"Arquivo não encontrado:\n{bat_path}")

    def build_ui(self):
        pad = {"padx": 10, "pady": 3}

        status_frame = ttk.LabelFrame(self.root, text="Radar do Mapa e Status em Tempo Real (v8)")
        status_frame.pack(fill="x", **pad)

        self.lbl_state = ttk.Label(
            status_frame, text="ESTADO: PARADO (Pressione F8 para Iniciar/Pausar)", font=("Segoe UI", 11, "bold"), foreground="#d9534f"
        )
        self.lbl_state.pack(anchor="w", padx=8, pady=2)

        self.lbl_vision = ttk.Label(
            status_frame, text="Radar: Aguardando... | Faixa: 0 px | Farol EVENT: 0 px | Grama Livre: 0 px", font=("Segoe UI", 9)
        )
        self.lbl_vision.pack(anchor="w", padx=8, pady=2)

        self.lbl_throws = ttk.Label(
            status_frame,
            text="Arremessos (+20): 0  |  Upgrades (E): 0  |  Mobs Guardados: 0  |  Cliques Barra (x2): 0",
            font=("Segoe UI", 9, "bold"),
            foreground="#0275d8",
        )
        self.lbl_throws.pack(anchor="w", padx=8, pady=2)

        preview_frame = ttk.LabelFrame(self.root, text="Visão do Bot (Captura da Janela do Roblox)")
        preview_frame.pack(fill="x", **pad)
        self.lbl_preview = ttk.Label(preview_frame, text="Abra o Roblox para visualizar a captura aqui")
        self.lbl_preview.pack(padx=5, pady=3)

        phase_frame = ttk.LabelFrame(self.root, text="🌍 Completar Fases do Animal Index (Ajuste Automático de Throw Power)")
        phase_frame.pack(fill="x", **pad)

        prow1 = ttk.Frame(phase_frame)
        prow1.pack(fill="x", padx=8, pady=2)
        ttk.Label(prow1, text="Fase Alvo (Throw Power):").pack(side="left")
        phase_names = [p["name"] for p in WORLD_PHASES]
        self.phase_combo = ttk.Combobox(prow1, values=phase_names, state="readonly", width=30)
        saved_phase = self.config.get("target_phase_name", phase_names[0])
        self.phase_combo.set(saved_phase if saved_phase in phase_names else phase_names[0])
        self.phase_combo.pack(side="left", padx=5)
        ttk.Button(prow1, text="🎯 Aplicar Fase no Jogo Agora", command=self.trigger_apply_phase_now).pack(side="left", padx=4)

        prow2 = ttk.Frame(phase_frame)
        prow2.pack(fill="x", padx=8, pady=2)
        self.auto_rotate_var = tk.BooleanVar(value=bool(self.config.get("auto_rotate_phases", False)))
        ttk.Checkbutton(
            prow2,
            text="🔄 Alternar automaticamente entre as fases incompletas a cada",
            variable=self.auto_rotate_var,
            command=self.save_config,
        ).pack(side="left")
        self.throws_per_phase_var = tk.IntVar(value=int(self.config.get("throws_per_phase", 15)))
        ttk.Spinbox(prow2, from_=3, to=200, textvariable=self.throws_per_phase_var, width=5, command=self.save_config).pack(side="left", padx=4)
        ttk.Label(prow2, text="arremessos").pack(side="left")

        extra_frame = ttk.LabelFrame(self.root, text="Automações Inteligentes (Upgrade E, Guardar Mob, Skip & Barra 2X)")
        extra_frame.pack(fill="x", **pad)

        self.auto_upgrade_var = tk.BooleanVar(value=bool(self.config.get("auto_upgrade_e", True)))
        ttk.Checkbutton(
            extra_frame,
            text="⬆️ Auto-Upgrade da Barra (Aperta 'E' ao voltar pro cercado/passar na plataforma amarela independente do valor $)",
            variable=self.auto_upgrade_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        self.auto_unequip_var = tk.BooleanVar(value=bool(self.config.get("auto_unequip_mob", True)))
        ttk.Checkbutton(
            extra_frame,
            text="🐾 Auto-Guardar Mob Novo da Mão + Limpar Tela Poluída (Tecla do Slot 1..0 + Fechar Popups)",
            variable=self.auto_unequip_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        self.auto_x2_var = tk.BooleanVar(value=bool(self.config.get("auto_pullup_x2", True)))
        ttk.Checkbutton(
            extra_frame,
            text="💪 Auto-Click no Círculo Roxo 'x2' (Dedo Amarelo) sempre que entrar no círculo da barra",
            variable=self.auto_x2_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        self.auto_skip_var = tk.BooleanVar(value=bool(self.config.get("auto_skip", True)))
        ttk.Checkbutton(
            extra_frame,
            text="⏩ Auto-Click em 'TAP TO SKIP' ao capturar animal no final do arremesso",
            variable=self.auto_skip_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        mode_frame = ttk.LabelFrame(self.root, text="Execução no seu Windows Principal (ou Sandbox Opcional)")
        mode_frame.pack(fill="x", **pad)

        self.restore_cursor_var = tk.BooleanVar(value=bool(self.config.get("restore_cursor", True)))
        ttk.Checkbutton(
            mode_frame,
            text="⚡ Funcionar direto no meu Windows (Devolve o cursor em 22ms após cada clique)",
            variable=self.restore_cursor_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        nav_frame = ttk.LabelFrame(self.root, text="Navegação 3 Estágios (Alinhamento por Setas + Farol EVENT/Mago/SELL)")
        nav_frame.pack(fill="x", **pad)

        row1 = ttk.Frame(nav_frame)
        row1.pack(fill="x", padx=8, pady=2)
        ttk.Label(row1, text="Direção para escanear o mapa ao sair do cercado:").pack(side="left")
        self.turn_dir_var = tk.StringVar(value=str(self.config.get("turn_dir", "right")))
        ttk.Radiobutton(row1, text="Direita (→)", variable=self.turn_dir_var, value="right", command=self.save_config).pack(side="left", padx=5)
        ttk.Radiobutton(row1, text="Esquerda (←)", variable=self.turn_dir_var, value="left", command=self.save_config).pack(side="left", padx=5)

        self.use_fixed_var = tk.BooleanVar(value=bool(self.config.get("use_fixed_walk_time", False)))
        ttk.Checkbutton(
            nav_frame,
            text="Limitar caminhada por tempo fixo (Desmarcado = navega pelo mapa até a barra 'TAP TO THROW!' abrir)",
            variable=self.use_fixed_var,
            command=self.save_config,
        ).pack(anchor="w", padx=8, pady=2)

        row2 = ttk.Frame(nav_frame)
        row2.pack(fill="x", padx=8, pady=2)
        ttk.Label(row2, text="Zona do Topo (+20):").pack(side="left")
        self.thresh_var = tk.DoubleVar(value=float(self.config.get("slider_threshold", 0.18)))
        ttk.Spinbox(row2, from_=0.04, to=0.30, increment=0.01, textvariable=self.thresh_var, width=5, command=self.save_config).pack(side="left", padx=4)
        ttk.Label(row2, text="| Espera Skip/Retorno (s):").pack(side="left", padx=4)
        self.wait_time_var = tk.DoubleVar(value=float(self.config.get("post_throw_wait", 4.5)))
        ttk.Spinbox(row2, from_=2.0, to=15.0, increment=0.5, textvariable=self.wait_time_var, width=5, command=self.save_config).pack(side="left", padx=4)
        self.walk_time_var = tk.DoubleVar(value=float(self.config.get("recorded_walk_time", 4.0)))

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=6)

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
        except Exception:
            pass

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

    def get_selected_phase_slider_x(self) -> float:
        sel = self.config.get("target_phase_name", "")
        for p in WORLD_PHASES:
            if p["name"] == sel:
                return float(p["slider_x"])
        return 0.3600

    def advance_to_next_incomplete_phase(self):
        incomplete = [p for p in WORLD_PHASES[1:] if not p["completed_default"]]
        if not incomplete:
            return
        self.current_phase_idx = (self.current_phase_idx + 1) % len(incomplete)
        next_p = incomplete[self.current_phase_idx]
        self.config["target_phase_name"] = next_p["name"]
        self.root.after(0, lambda: self.phase_combo.set(next_p["name"]))
        self.needs_power_apply = True

    def start_walking_forward(self):
        if self.hwnd:
            focus_roblox_window(self.hwnd)
        if "w" not in self.active_keys:
            self.active_keys.add("w")
        send_direct_key("w", True)

    def stop_walking_forward(self):
        if "w" in self.active_keys:
            self.active_keys.discard("w")
        send_direct_key("w", False)

    def steer_while_walking(self, target_x: float):
        """
        Gira a câmera com pulsos proporcionais nas setas `left` / `right` para alinhar `target_x`
        com o centro (`0.52`). Só permite segurar `W` quando `abs(target_x - 0.52) <= 0.14`.
        """
        error = target_x - 0.52
        if abs(error) > 0.14:
            # Desalinhado: solta W, gira a câmera primeiro até ficar de frente para a pista
            self.stop_walking_forward()
            turn_key = "right" if error > 0 else "left"
            pulse_dur = min(0.065, max(0.025, abs(error) * 0.14))
            self.pulse_turn_key(turn_key, duration=pulse_dur)
            return False

        # Alinhado dentro da tolerância: micro-correção suave de câmera mantendo W pressionado
        if abs(error) > 0.045:
            turn_key = "right" if error > 0 else "left"
            pulse_dur = min(0.028, max(0.012, abs(error) * 0.10))
            send_direct_key(turn_key, True)
            time.sleep(pulse_dur)
            send_direct_key(turn_key, False)
        return True

    def escape_cluttered_spawn_maneuver(self):
        if self.hwnd:
            focus_roblox_window(self.hwnd)
        if self.config.get("auto_upgrade_e", True):
            tap_key("e", 0.03)
            self.upgrade_attempts += 1
        turn_key = "right" if self.config["turn_dir"] == "right" else "left"
        send_direct_key(turn_key, True)
        time.sleep(0.085)
        send_direct_key(turn_key, False)

    def unstick_maneuver(self, attempt: int = 0):
        """
        Alterna o lado do desvio (`a` nas tentativas pares, `d` nas ímpares),
        dá um breve recuo com `s` (0.15s) antes de pular (`space` + tecla lateral por 0.25s)
        e volta a pressionar `w`.
        """
        if self.hwnd:
            focus_roblox_window(self.hwnd)
        self.stop_walking_forward()
        if self.config.get("auto_upgrade_e", True):
            tap_key("e", 0.03)

        # Breve recuo com S
        send_direct_key("s", True)
        time.sleep(0.15)
        send_direct_key("s", False)

        # Pulo + passo lateral alternado (a nas pares, d nas ímpares)
        side_key = "a" if (attempt % 2 == 0) else "d"
        send_direct_key("space", True)
        send_direct_key(side_key, True)
        time.sleep(0.25)
        send_direct_key("space", False)
        send_direct_key(side_key, False)

        # Volta a pressionar W
        self.start_walking_forward()

    def pulse_turn_key(self, key_name: str, duration: float = 0.065):
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
        last_e_upgrade_time = 0.0
        unequip_retry_with_click = False
        unstick_attempt = 0
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

            # Durante is_power_bar == True, suspende o redimensionamento de imagem do preview (arr=None)
            # para maximizar o FPS e reduzir o atraso do clique no topo!
            if loop_start - last_preview_time > 0.25:
                last_preview_time = loop_start
                preview_arr = None if info["is_power_bar"] else arr
                self.update_ui_status(None, info, preview_arr)

            if not self.running:
                time.sleep(0.05)
                continue

            if self.state == "ARREMESSANDO_+20" and not info["is_power_bar"]:
                self.release_all_keys()
                self.state = "BUSCANDO_ROTA_NO_MAPA"
                state_start_time = time.time()
                prev_slider_pos = None

            # =================================================================
            # 0) FECHAR POPUPS ABERTOS POR ENGANO (Sell Animals / Animal Index / Throw Power)
            # =================================================================
            if info["modal_name"] is not None and not self.needs_power_apply:
                self.release_all_keys()
                modal_name = info["modal_name"]
                cx, cy = info["modal_close_pos"]
                click_roblox_pos(
                    self.hwnd,
                    cx,
                    cy,
                    restore_cursor=self.config.get("restore_cursor", True),
                    also_press_space=False,
                )
                time.sleep(0.20)
                # Se abriu "Sell Animals" sem querer ao pisar no círculo vermelho de venda,
                # dá um pequeno passo para trás/lado para sair da área de venda e não reabrir!
                if modal_name == "SELL_ANIMALS":
                    focus_roblox_window(self.hwnd)
                    send_direct_key("s", True)
                    time.sleep(0.25)
                    send_direct_key("s", False)
                    self.state = "BUSCANDO_ROTA_NO_MAPA"
                continue

            # =================================================================
            # 1) APLICAR MUDANÇA DE FASE (THROW POWER SLIDER) SE SOLICITADO
            # =================================================================
            if self.needs_power_apply and not info["is_power_bar"] and not info["is_pullup"]:
                self.release_all_keys()
                self.state = "AJUSTANDO_THROW_POWER_FASE"
                target_sx = self.get_selected_phase_slider_x()
                drag_slider_to_pos(
                    self.hwnd,
                    target_sx,
                    restore_cursor=self.config.get("restore_cursor", True),
                )
                self.needs_power_apply = False
                self.state = "BUSCANDO_ROTA_NO_MAPA"
                continue

            # =================================================================
            # 2) MODO TREINO DE BARRA (AO ENTRAR NO CÍRCULO DA BARRA -> CLICA NO 2X!)
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
            # 3) BARRA VERTICAL DE ARREMESSO ("TAP TO THROW!")
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
                    # Verifica direção do movimento: se slider_pos > prev_slider_pos (barrinha descendo),
                    # ignora o clique e aguarda ela bater na base e subir novamente!
                    if prev_slider_pos is not None and slider_pos > prev_slider_pos + 0.002:
                        prev_slider_pos = slider_pos
                        continue

                    effective_pos = slider_pos
                    if prev_slider_pos is not None and slider_pos < prev_slider_pos:
                        vel_up = prev_slider_pos - slider_pos
                        effective_pos = max(0.0, slider_pos - vel_up * 0.65)
                    prev_slider_pos = slider_pos

                    if effective_pos <= thresh:
                        # Sem also_press_space=True para não pular nem duplicar input
                        click_roblox_pos(
                            self.hwnd,
                            0.50,
                            0.55,
                            restore_cursor=self.config.get("restore_cursor", True),
                            also_press_space=False,
                        )
                        self.throw_count += 1
                        self.throws_in_current_phase += 1
                        if (
                            self.config.get("auto_rotate_phases", False)
                            and self.throws_in_current_phase >= int(self.config.get("throws_per_phase", 15))
                        ):
                            self.throws_in_current_phase = 0
                            self.advance_to_next_incomplete_phase()

                        self.state = "TAP_TO_SKIP_E_RETORNO"
                        state_start_time = time.time()
                        last_skip_click = time.time()
                        prev_slider_pos = None
                        time.sleep(0.20)
                continue

            # =================================================================
            # 4) APÓS O ARREMESSO: CLICA EM "TAP TO SKIP", GUARDA MOB E DÁ UPGRADE (E)
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
                    if self.config.get("auto_upgrade_e", True):
                        focus_roblox_window(self.hwnd)
                        tap_key("e", 0.035)
                        self.upgrade_attempts += 1
                        last_e_upgrade_time = time.time()
                    self.state = "BUSCANDO_ROTA_NO_MAPA"
                    state_start_time = time.time()
                time.sleep(0.04)
                continue

            # =================================================================
            # 5) GUARDAR MOB EQUIPADO NA MÃO (HOTBAR DINÂMICA + FALLBACK CLIQUE)
            # =================================================================
            if self.config.get("auto_unequip_mob", True) and info["mob_equipped"] and info["mob_slot_x"] is not None:
                if time.time() - last_unequip_time >= 0.35:
                    self.release_all_keys()
                    self.state = "GUARDANDO_MOB_DA_MAO"
                    focus_roblox_window(self.hwnd)
                    if not unequip_retry_with_click and info["mob_slot_key"] is not None:
                        tap_key(info["mob_slot_key"], 0.035)
                        # Se no frame seguinte ainda estiver equipado, o próximo ciclo usa o clique como fallback
                        unequip_retry_with_click = True
                    else:
                        click_roblox_pos(
                            self.hwnd,
                            info["mob_slot_x"],
                            info["mob_slot_y"],
                            restore_cursor=self.config.get("restore_cursor", True),
                            also_press_space=False,
                        )
                        unequip_retry_with_click = False
                    self.unequip_count += 1
                    last_unequip_time = time.time()
                    time.sleep(0.20)
                    self.state = "BUSCANDO_ROTA_NO_MAPA"
                    continue
            else:
                unequip_retry_with_click = False

            # =================================================================
            # 6) AUTO-UPGRADE (TECLA 'E') SEMPRE QUE O BOTÃO AMARELO DE UPGRADE ESTIVER VISÍVEL
            # =================================================================
            if self.config.get("auto_upgrade_e", True) and info["yellow_pad_px"] >= 500:
                if time.time() - last_e_upgrade_time >= 1.8:
                    focus_roblox_window(self.hwnd)
                    tap_key("e", 0.035)
                    self.upgrade_attempts += 1
                    last_e_upgrade_time = time.time()

            # =================================================================
            # 7) NAVEGAÇÃO NO MAPA COM TRAVA DE ALINHAMENTO POR SETAS
            # =================================================================
            if info["nav_stage"] != "SEARCHING":
                if not self.state.startswith("NAVEGANDO_"):
                    walk_start_time = time.time()
                    last_sig_check_time = time.time()
                    prev_frame_sig = info["frame_sig"]
                    unstick_attempt = 0

                self.state = f"NAVEGANDO_{info['nav_stage']}"
                elapsed_walk = time.time() - walk_start_time

                if self.config["use_fixed_walk_time"] and elapsed_walk >= float(self.config["recorded_walk_time"]):
                    self.release_all_keys()
                    self.state = "AGUARDANDO_BARRA"
                    state_start_time = time.time()
                    continue

                # Alinha câmera com setas left/right; só segura W se abs(target_x - 0.52) <= 0.14
                aligned = self.steer_while_walking(info["target_x"])
                if aligned:
                    if "w" not in self.active_keys or (time.time() - last_w_refresh > 0.30):
                        self.start_walking_forward()
                        last_w_refresh = time.time()

                    # Radar Anti-Colisão (Optical Flow na faixa lateral inferior do chão)
                    if time.time() - last_sig_check_time > 1.1:
                        if prev_frame_sig is not None:
                            diff = float(np.mean(np.abs(info["frame_sig"] - prev_frame_sig)))
                            if diff < 3.2:
                                self.unstick_maneuver(unstick_attempt)
                                unstick_attempt += 1
                        prev_frame_sig = info["frame_sig"]
                        last_sig_check_time = time.time()
                else:
                    last_sig_check_time = time.time()
                    prev_frame_sig = info["frame_sig"]

                time.sleep(0.02)
                continue

            # =================================================================
            # 8) ESCANEANDO O MAPA / SAINDO DE TELA POLUÍDA POR MOBS GIGANTES
            # =================================================================
            self.release_all_keys()
            if info["is_screen_cluttered"]:
                self.state = "LIMPANDO_VISAO_POLUIDA"
                self.escape_cluttered_spawn_maneuver()
            else:
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
                mob_txt = f"SIM (Slot {info['mob_slot_key']})" if info["mob_equipped"] else "Não"
                self.lbl_vision.config(
                    text=(
                        f"Estágio: {info['nav_stage']} | Alvo X={info['target_x']:.2f} | "
                        f"Faixa: {info['orange_total']} px | Farol: {info['event_px'] + info['booth_px'] + info['sell_px']} px | "
                        f"Mob Mão: {mob_txt} | Barra: {bar_txt}"
                    )
                )
                self.lbl_throws.config(
                    text=(
                        f"Arremessos (+20): {self.throw_count}  |  Upgrades (E): {self.upgrade_attempts}  |  "
                        f"Mobs Guardados: {self.unequip_count}  |  Cliques Barra (x2): {self.x2_click_count}"
                    )
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
