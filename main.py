import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import socket
import threading
import pygame
import json
from datetime import datetime
import os
from collections import deque
import math
import statistics
import subprocess
import cv2
import numpy as np
import fitz  # PyMuPDF

# === CONFIGURAÇÕES ===
PORTA_UDP = 5000
TIMEOUT = 0.02
LP_ALPHA = 0.9
TILT_THRESHOLD = 80.0
VIB_THRESHOLD = 1.5
WINDOW_SIZE = 20
gravacao_inicio = None
gravacao_fim = None

# === ÁUDIO ===
pygame.mixer.init()
def tocar_alerta(nome_arquivo):
    if os.path.isfile(nome_arquivo):
        pygame.mixer.music.load(nome_arquivo)
        pygame.mixer.music.play()

# === VARIÁVEIS GLOBAIS ===
running = False
thread = None
recording = False
video_writer = None
video_filename = None
frames_buffer = []

# Novo estado para saber se está encerrado
encerrado = False

tempo = []
tilts = deque(maxlen=WINDOW_SIZE)
vibracoes = deque(maxlen=WINDOW_SIZE)
alerts = []

tilts_all = []
vibracoes_all = []

tilt_alerted = False
vib_alerted = False
t = 0
gravity = [0.0, 0.0, 9.81]

# === GRAVAÇÃO DE VÍDEO ===
def iniciar_gravacao():
    global recording, video_writer, video_filename, frames_buffer, gravacao_inicio
    if recording:
        return
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_filename = f"gravacao_graficos_{now}.mp4"
    recording = True
    frames_buffer = []
    gravacao_inicio = datetime.now()  # marca o tempo de início
    print(f"Iniciando gravação: {video_filename}")

def finalizar_gravacao():
    global recording, video_writer, frames_buffer, gravacao_fim
    if not recording:
        return
    recording = False
    gravacao_fim = datetime.now()  # marca o tempo de fim

    if len(frames_buffer) == 0:
        print("Nenhum frame capturado para gravação")
        return
    try:
        duracao_segundos = (gravacao_fim - gravacao_inicio).total_seconds()
        fps = len(frames_buffer) / duracao_segundos if duracao_segundos > 0 else 10

        print(f"Duração real: {duracao_segundos:.2f}s | FPS calculado: {fps:.2f}")

        height, width, channels = frames_buffer[0].shape
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(video_filename, fourcc, fps, (width, height))
        for frame in frames_buffer:
            video_writer.write(frame)
        video_writer.release()
        video_writer = None
        print(f"Gravação finalizada: {video_filename} com {len(frames_buffer)} frames")
    except Exception as e:
        print(f"Erro ao finalizar gravação: {e}")
        if video_writer:
            video_writer.release()

def capturar_frame_grafico():
    global frames_buffer
    if not recording:
        return
    
    try:
        canvas.draw()
        canvas.flush_events()
        
        # Método atualizado para versões mais recentes do matplotlib
        buf = canvas.buffer_rgba()
        buf = np.asarray(buf)
        buf = buf.reshape(canvas.get_width_height()[::-1] + (4,))
        
        # Remove o canal alpha (RGBA -> RGB)
        frame_rgb = buf[:, :, :3]
        
        # Converte RGB para BGR (formato do OpenCV)
        frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        
        # Redimensiona para tamanho padrão se necessário
        frame = cv2.resize(frame, (800, 600))
        
        # Adiciona ao buffer
        frames_buffer.append(frame.copy())
        
        # Limita o buffer para evitar uso excessivo de memória
        if len(frames_buffer) > 1000:
            frames_buffer.pop(0)
            
    except Exception as e:
        print(f"Erro ao capturar frame: {e}")
        # Fallback para versões mais antigas do matplotlib
        try:
            buf = np.frombuffer(canvas.tostring_rgb(), dtype=np.uint8)
            buf = buf.reshape(canvas.get_width_height()[::-1] + (3,))
            frame = cv2.cvtColor(buf, cv2.COLOR_RGB2BGR)
            frame = cv2.resize(frame, (800, 600))
            frames_buffer.append(frame.copy())
            if len(frames_buffer) > 1000:
                frames_buffer.pop(0)
        except Exception as e2:
            print(f"Erro no fallback: {e2}")

# === RELATÓRIO COM VÍDEO ANEXADO USANDO PyMuPDF ===
def gerar_relatorio():
    global video_filename, gravacao_inicio, gravacao_fim

    finalizar_gravacao()

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"relatorio_{now}.pdf"

    # Estatísticas
    tilt_list = [v for v in tilts_all if not math.isnan(v)] if grafico_tilt_var.get() else []
    vib_list = [v for v in vibracoes_all if not math.isnan(v)] if grafico_vib_var.get() else []
    tilt_media = sum(tilt_list) / len(tilt_list) if tilt_list else 0
    vib_media = sum(vib_list) / len(vib_list) if vib_list else 0
    tilt_max = max(tilt_list) if tilt_list else 0
    tilt_min = min(tilt_list) if tilt_list else 0
    vib_max = max(vib_list) if vib_list else 0
    vib_min = min(vib_list) if vib_list else 0
    tilt_std = statistics.stdev(tilt_list) if len(tilt_list) > 1 else 0
    vib_std = statistics.stdev(vib_list) if len(vib_list) > 1 else 0

    duracao_real = (gravacao_fim - gravacao_inicio).total_seconds() if gravacao_inicio and gravacao_fim else len(frames_buffer)/10

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4

    cor_laranja = (1, 0.5, 0)
    cor_preta = (0, 0, 0)
    cor_cinza = (0.3, 0.3, 0.3)
    cor_cinza_claro = (0.9, 0.9, 0.9)

    y_pos = 800
    desenhou_estatisticas = False  # <- controle do espaço em branco

    # Cabeçalho
    logo_path = os.path.join(os.path.dirname(__file__), 'riggy-logo.jpeg')
    if os.path.isfile(logo_path):
        try:
            logo_rect = fitz.Rect(50, y_pos-60, 110, y_pos)
            page.insert_image(logo_rect, filename=logo_path)
        except:
            pass

    page.insert_text((130, y_pos-20), "RELATÓRIO RIGGY", fontsize=20, color=cor_laranja)
    page.insert_text((130, y_pos-40), "UDP SensaGram - Monitoramento de Sensores", fontsize=12, color=cor_cinza)
    page.draw_line(fitz.Point(50, y_pos-70), fitz.Point(545, y_pos-70), color=cor_laranja, width=2)
    y_pos -= 90

    # Informações gerais
    info_rect = fitz.Rect(50, y_pos-80, 545, y_pos)
    page.draw_rect(info_rect, color=cor_cinza_claro, fill=cor_cinza_claro)
    page.draw_rect(info_rect, color=cor_cinza, width=1)
    page.insert_text((60, y_pos-15), "INFORMAÇÕES GERAIS", fontsize=12, color=cor_laranja)
    page.insert_text((60, y_pos-35), f"Data e Hora: {datetime.now():%d/%m/%Y %H:%M:%S}", fontsize=11, color=cor_preta)
    page.insert_text((60, y_pos-50), f"Pontos Coletados: {len(tempo)}", fontsize=11, color=cor_preta)
    page.insert_text((300, y_pos-35), f"Alertas de Inclinação: {sum(1 for a in alerts if a[0]=='tilt') if grafico_tilt_var.get() else 0}", fontsize=11, color=cor_preta)
    page.insert_text((300, y_pos-50), f"Alertas de Vibração: {sum(1 for a in alerts if a[0]=='vibração') if grafico_vib_var.get() else 0}", fontsize=11, color=cor_preta)
    y_pos -= 100

    # Estatísticas de inclinação
    if grafico_tilt_var.get():
        desenhou_estatisticas = True
        tilt_rect = fitz.Rect(50, y_pos-120, 545, y_pos)
        page.draw_rect(tilt_rect, color=cor_cinza_claro, fill=cor_cinza_claro)
        page.draw_rect(tilt_rect, color=cor_cinza, width=1)
        page.insert_text((60, y_pos-15), "📐 ESTATÍSTICAS DE INCLINAÇÃO (°)", fontsize=12, color=cor_laranja)
        page.insert_text((60, y_pos-35), f"Média: {tilt_media:.2f}°", fontsize=11, color=cor_preta)
        page.insert_text((60, y_pos-50), f"Máximo: {tilt_max:.2f}°", fontsize=11, color=cor_preta)
        page.insert_text((60, y_pos-65), f"Mínimo: {tilt_min:.2f}°", fontsize=11, color=cor_preta)
        page.insert_text((300, y_pos-35), f"Desvio Padrão: {tilt_std:.2f}°", fontsize=11, color=cor_preta)
        page.insert_text((300, y_pos-50), f"Limite Configurado: {TILT_THRESHOLD:.1f}°", fontsize=11, color=cor_preta)
        status_tilt = "DENTRO DO LIMITE" if tilt_max < TILT_THRESHOLD else "LIMITE ULTRAPASSADO"
        cor_status = (0, 0.7, 0) if tilt_max < TILT_THRESHOLD else (0.8, 0, 0)
        page.insert_text((300, y_pos-65), f"Status: {status_tilt}", fontsize=11, color=cor_status)
        y_pos -= 140

    # Estatísticas de vibração
    if grafico_vib_var.get():
        desenhou_estatisticas = True
        vib_rect = fitz.Rect(50, y_pos-120, 545, y_pos)
        page.draw_rect(vib_rect, color=cor_cinza_claro, fill=cor_cinza_claro)
        page.draw_rect(vib_rect, color=cor_cinza, width=1)
        page.insert_text((60, y_pos-15), "📳 ESTATÍSTICAS DE VIBRAÇÃO (g)", fontsize=12, color=cor_laranja)
        page.insert_text((60, y_pos-35), f"Média: {vib_media:.3f}g", fontsize=11, color=cor_preta)
        page.insert_text((60, y_pos-50), f"Máximo: {vib_max:.3f}g", fontsize=11, color=cor_preta)
        page.insert_text((60, y_pos-65), f"Mínimo: {vib_min:.3f}g", fontsize=11, color=cor_preta)
        page.insert_text((300, y_pos-35), f"Desvio Padrão: {vib_std:.3f}g", fontsize=11, color=cor_preta)
        page.insert_text((300, y_pos-50), f"Limite Configurado: {VIB_THRESHOLD:.1f}g", fontsize=11, color=cor_preta)
        status_vib = "DENTRO DO LIMITE" if vib_max < VIB_THRESHOLD else "LIMITE ULTRAPASSADO"
        cor_status = (0, 0.7, 0) if vib_max < VIB_THRESHOLD else (0.8, 0, 0)
        page.insert_text((300, y_pos-65), f"Status: {status_vib}", fontsize=11, color=cor_status)
        y_pos -= 140

    # Se nenhuma estatística foi desenhada, corrige o y_pos
    if not desenhou_estatisticas:
        y_pos -= 40  # distância abaixo de "Informações Gerais"

    # Seção de vídeo
    if video_filename and os.path.isfile(video_filename):
        video_rect = fitz.Rect(50, y_pos-100, 545, y_pos)
        page.draw_rect(video_rect, color=(0.1, 0.1, 0.1), fill=(0.1, 0.1, 0.1))
        page.draw_rect(video_rect, color=cor_laranja, width=2)
        page.insert_text((60, y_pos-15), "🎥 GRAVAÇÃO DOS GRÁFICOS", fontsize=12, color=cor_laranja)
        page.insert_text((60, y_pos-35), f"Arquivo: {video_filename}", fontsize=11, color=(1, 1, 1))
        page.insert_text((60, y_pos-50), f"Frames Capturados: {len(frames_buffer)}", fontsize=11, color=(1, 1, 1))
        page.insert_text((60, y_pos-65), f"Duração Aproximada: {duracao_real:.1f} segundos", fontsize=11, color=(1, 1, 1))
        try:
            with open(video_filename, 'rb') as video_file:
                video_bytes = video_file.read()
            doc.embfile_add(video_filename, video_bytes, filename=os.path.basename(video_filename))
            page.insert_text((400, y_pos-35), "📎 VÍDEO ANEXADO", fontsize=12, color=cor_laranja)
            page.insert_text((400, y_pos-50), "Clique no ícone de anexo", fontsize=10, color=(0.8, 0.8, 0.8))
            page.insert_text((400, y_pos-65), "no seu leitor de PDF", fontsize=10, color=(0.8, 0.8, 0.8))
        except Exception as e:
            print(f"Erro ao anexar vídeo: {e}")
            page.insert_text((400, y_pos-35), "❌ ERRO NO ANEXO", fontsize=12, color=(0.8, 0, 0))
            page.insert_text((400, y_pos-50), "Vídeo salvo separadamente", fontsize=10, color=(0.8, 0.8, 0.8))
        y_pos -= 30

    # Rodapé
    page.draw_line(fitz.Point(50, 80), fitz.Point(545, 80), color=cor_laranja, width=1)
    page.insert_text((50, 60), "Gerado por Riggy - UDP SensaGram", fontsize=10, color=cor_cinza)
    page.insert_text((50, 45), f"Relatório gerado em {datetime.now():%d/%m/%Y às %H:%M:%S}", fontsize=9, color=cor_cinza)
    page.insert_text((400, 60), f"Página 1 de 1", fontsize=10, color=cor_cinza)

    # --- NOVO: Inserir gráficos completos (por tempo) em nova página ---
    graficos_paths = salvar_graficos_completos_para_pdf(tilts_all, vibracoes_all, grafico_tilt_var.get(), grafico_vib_var.get())
    if graficos_paths:
        page_graficos = doc.new_page(width=595, height=842)
        y_graf = 800
        page_graficos.insert_text((60, y_graf-20), "GRÁFICOS COMPLETOS POR TEMPO", fontsize=16, color=cor_laranja)
        y_graf -= 40
        for path in graficos_paths:
            try:
                img = fitz.Pixmap(path)
                img_width = 400
                img_height = int(img.height * (img_width / img.width))
                img_rect = fitz.Rect((595-img_width)//2, y_graf-img_height, (595+img_width)//2, y_graf)
                page_graficos.insert_image(img_rect, filename=path)
                y_graf -= (img_height + 20)
            except Exception as e:
                print(f"Erro ao inserir gráfico no PDF: {e}")
    # --- FIM NOVO ---

    doc.save(pdf_filename)
    doc.close()

    # Remove arquivos temporários dos gráficos
    for path in graficos_paths:
        try:
            os.remove(path)
        except Exception as e:
            print(f"Erro ao remover arquivo temporário {path}: {e}")

    try:
        os.startfile(pdf_filename)
    except:
        pass

    print(f"Relatório gerado: {pdf_filename}")
    if video_filename and os.path.isfile(video_filename):
        print(f"Vídeo salvo: {video_filename}")

# === THREAD UDP ===
def servidor_udp():
    global t, running, gravity, tilt_alerted, vib_alerted
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORTA_UDP))
    sock.settimeout(TIMEOUT)

    # Calibração da gravidade
    for _ in range(WINDOW_SIZE):
        if not running: return
        try:
            data, _ = sock.recvfrom(1024)
            obj = json.loads(data.decode())
            if 'accelerometer' in obj.get('type',''):
                ax, ay, az = obj.get('values')[:3]
                gravity[0] = LP_ALPHA*gravity[0] + (1-LP_ALPHA)*ax
                gravity[1] = LP_ALPHA*gravity[1] + (1-LP_ALPHA)*ay
                gravity[2] = LP_ALPHA*gravity[2] + (1-LP_ALPHA)*az
        except:
            pass

    while running:
        try:
            data, _ = sock.recvfrom(1024)
            obj = json.loads(data.decode())
        except:
            continue

        if 'accelerometer' not in obj.get('type',''):
            continue

        ax, ay, az = obj.get('values')[:3]

        # Filtro de gravidade
        gravity[0] = LP_ALPHA*gravity[0] + (1-LP_ALPHA)*ax
        gravity[1] = LP_ALPHA*gravity[1] + (1-LP_ALPHA)*ay
        gravity[2] = LP_ALPHA*gravity[2] + (1-LP_ALPHA)*az
        gx, gy, gz = gravity

        # Inclinação
        mag = math.sqrt(gx*gx + gy*gy + gz*gz)
        cos_t = gz/mag if mag else 1
        cos_t = max(-1.0, min(1.0, cos_t))
        tilt_angle = math.degrees(math.acos(cos_t))
        tilts.append(tilt_angle)
        tilts_all.append(tilt_angle)

        # Vibração com suavização
        total_acc = math.sqrt(ax*ax + ay*ay + az*az)
        vib = abs(total_acc - 9.81)
        vibracoes.append(vib)
        vibracoes_all.append(vib)
        avg_vib = sum(vibracoes) / len(vibracoes) if vibracoes else 0

        tempo.append(t)
        t += 1

        # Alerta de inclinação
        if grafico_tilt_var.get():
            avg_tilt = sum(tilts) / len(tilts) if tilts else 0
            if avg_tilt >= TILT_THRESHOLD and not tilt_alerted:
                alerts.append(('tilt', datetime.now(), avg_tilt))
                tocar_alerta('alerta_inclinacao.mp3')
                tilt_alerted = True
            if avg_tilt < TILT_THRESHOLD - 20:
                tilt_alerted = False

        # Alerta de vibração
        if grafico_vib_var.get():
            if avg_vib >= VIB_THRESHOLD and not vib_alerted:
                alerts.append(('vibração', datetime.now(), avg_vib))
                tocar_alerta('alerta_vibracao.mp3')
                vib_alerted = True
            if avg_vib < VIB_THRESHOLD - 0.3:
                vib_alerted = False

# === INTERFACE ===
ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('dark-blue')

# Cores customizadas
COR_LARANJA = '#FF8800'
COR_PRETO = '#181818'
COR_CINZA = '#232323'
COR_TEXTO = '#FFFFFF'

app = ctk.CTk()
app.title('Riggy - UDP SensaGram')
app.geometry('900x700')
app.configure(bg=COR_PRETO)

# Define o ícone da janela
ico_path = os.path.join(os.path.dirname(__file__), 'riggy-logo.ico')
if os.path.isfile(ico_path):
    try:
        app.iconbitmap(ico_path)
    except Exception:
        pass

# Função para obter o IP local
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def get_wifi_ssid():
    if os.name == 'nt':  # Windows
        try:
            output = subprocess.check_output(['netsh', 'wlan', 'show', 'interfaces'], encoding='utf-8', errors='ignore')
            for line in output.split('\n'):
                if 'SSID' in line and 'BSSID' not in line:
                    ssid = line.split(':', 1)[1].strip()
                    if ssid and ssid.lower() != 'ssid':
                        return ssid
        except Exception:
            pass
    return 'N/A'

# Layout principal
frame_titulo = ctk.CTkFrame(app, fg_color='transparent')
frame_titulo.pack(fill='x', pady=(10, 0))
label_titulo = ctk.CTkLabel(frame_titulo, text='Riggy', font=('Segoe UI', 24, 'bold'), text_color=COR_LARANJA)
label_titulo.pack(anchor='center')

local_ip = get_local_ip()
wifi_ssid = get_wifi_ssid()
label_ip = ctk.CTkLabel(frame_titulo, text=f'ip: {local_ip}  port: {PORTA_UDP}  wifi: {wifi_ssid}', font=('Segoe UI', 14), text_color=COR_TEXTO)
label_ip.pack(anchor='center', pady=(2, 0))

frame_principal = ctk.CTkFrame(app, fg_color='transparent')
frame_principal.pack(fill='both', expand=True, padx=20, pady=10)

frame_esquerdo = ctk.CTkFrame(frame_principal, fg_color=COR_CINZA, corner_radius=16, width=300)
frame_esquerdo.pack(side='left', fill='y', padx=(0, 20), pady=0)
frame_esquerdo.pack_propagate(False)

frame_direito = ctk.CTkFrame(frame_principal, fg_color=COR_CINZA, corner_radius=16)
frame_direito.pack(side='right', fill='both', expand=True, pady=0)

# Checkboxes de gráficos
checkbox_frame = ctk.CTkFrame(frame_esquerdo, fg_color='transparent')
checkbox_frame.pack(fill='x', pady=(10, 0))

grafico_tilt_var = ctk.BooleanVar(value=False)
grafico_vib_var = ctk.BooleanVar(value=False)

def on_checkbox_change():
    atualizar_inputs_limites()
    atualizar_estado_iniciar()
    update_graph()

checkbox_tilt = ctk.CTkCheckBox(
    checkbox_frame, text='Inclinação', variable=grafico_tilt_var,
    command=on_checkbox_change, font=('Segoe UI', 13), text_color=COR_TEXTO
)
checkbox_tilt.pack(side='left', padx=10, pady=5)

checkbox_vib = ctk.CTkCheckBox(
    checkbox_frame, text='Vibração', variable=grafico_vib_var,
    command=on_checkbox_change, font=('Segoe UI', 13), text_color=COR_TEXTO
)
checkbox_vib.pack(side='left', padx=10, pady=5)

status_label = ctk.CTkLabel(frame_esquerdo, text='Pronto para iniciar', font=('Segoe UI', 16, 'bold'), text_color=COR_LARANJA)
status_label.pack(pady=(10, 20))

# Gráficos
fig, axs = plt.subplots(2, 1, figsize=(7, 5))
fig.patch.set_facecolor(COR_CINZA)
fig.tight_layout(pad=3.0)
canvas = FigureCanvasTkAgg(fig, frame_direito)

plt.rcParams['axes.facecolor'] = COR_CINZA
plt.rcParams['figure.facecolor'] = COR_CINZA
plt.rcParams['axes.labelcolor'] = COR_TEXTO
plt.rcParams['xtick.color'] = COR_TEXTO
plt.rcParams['ytick.color'] = COR_TEXTO
plt.rcParams['axes.edgecolor'] = COR_PRETO
plt.rcParams['text.color'] = COR_TEXTO

def update_graph():
    global encerrado
    for ax in axs:
        ax.clear()
        ax.set_visible(False)

    show_tilt = grafico_tilt_var.get()
    show_vib = grafico_vib_var.get()

    # Se não está rodando e está encerrado, mostrar gráfico por tempo
    if encerrado:
        if show_tilt:
            axs[0].set_visible(True)
            if tilts_all:
                axs[0].plot(list(range(len(tilts_all))), tilts_all, color=COR_LARANJA, linewidth=2)
            axs[0].set_ylim(0, 100)
            axs[0].set_title('Inclinação (°) por tempo', color=COR_LARANJA, fontsize=12, fontweight='bold')
            axs[0].set_ylabel('Grau', color=COR_TEXTO)
            axs[0].set_facecolor(COR_CINZA)
        if show_vib:
            idx = 1 if show_tilt else 0
            axs[idx].set_visible(True)
            if vibracoes_all:
                axs[idx].plot(list(range(len(vibracoes_all))), vibracoes_all, color='#FFB266', linewidth=2)
            axs[idx].set_ylim(0, 5)
            axs[idx].set_title('Vibração (g) por tempo', color=COR_LARANJA, fontsize=12, fontweight='bold')
            axs[idx].set_ylabel('g', color=COR_TEXTO)
            axs[idx].set_facecolor(COR_CINZA)
        fig.tight_layout(pad=3.0)
        canvas.draw()
        return

    if not show_tilt and not show_vib:
        canvas.draw()
        if running:
            app.after(50, update_graph)
        return

    if show_tilt and show_vib:
        axs[0].set_visible(True)
        axs[1].set_visible(True)
        if tilts:
            pts = list(range(len(tilts)))
            axs[0].plot(pts, list(tilts), color=COR_LARANJA, linewidth=2)
        axs[0].set_ylim(0, 100)
        axs[0].set_title('Inclinação (°)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[0].set_ylabel('Grau', color=COR_TEXTO)
        axs[0].set_facecolor(COR_CINZA)

        if vibracoes:
            pts = list(range(len(vibracoes)))
            axs[1].plot(pts, list(vibracoes), color='#FFB266', linewidth=2)
        axs[1].set_ylim(0, 5)
        axs[1].set_title('Vibração (g)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[1].set_ylabel('g', color=COR_TEXTO)
        axs[1].set_facecolor(COR_CINZA)

    elif show_tilt:
        axs[0].set_visible(True)
        if tilts:
            pts = list(range(len(tilts)))
            axs[0].plot(pts, list(tilts), color=COR_LARANJA, linewidth=2)
        axs[0].set_ylim(0, 100)
        axs[0].set_title('Inclinação (°)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[0].set_ylabel('Grau', color=COR_TEXTO)
        axs[0].set_facecolor(COR_CINZA)

    elif show_vib:
        axs[0].set_visible(True)
        if vibracoes:
            pts = list(range(len(vibracoes)))
            axs[0].plot(pts, list(vibracoes), color='#FFB266', linewidth=2)
        axs[0].set_ylim(0, 5)
        axs[0].set_title('Vibração (g)', color=COR_LARANJA, fontsize=12, fontweight='bold')
        axs[0].set_ylabel('g', color=COR_TEXTO)
        axs[0].set_facecolor(COR_CINZA)

    fig.tight_layout(pad=3.0)
    canvas.draw()
    
    # Captura frame para gravação
    if recording:
        capturar_frame_grafico()
    
    if running:
        app.after(50, update_graph)

# Função para salvar gráficos completos para PDF
def salvar_graficos_completos_para_pdf(tilts_all, vibracoes_all, show_tilt, show_vib):
    paths = []
    if show_tilt and tilts_all:
        fig_tilt, ax_tilt = plt.subplots(figsize=(6, 3))
        ax_tilt.plot(list(range(len(tilts_all))), tilts_all, color=COR_LARANJA, linewidth=2)
        ax_tilt.set_ylim(0, 100)
        ax_tilt.set_title('Inclinação (°) por tempo', color=COR_LARANJA, fontsize=12, fontweight='bold')
        ax_tilt.set_ylabel('Grau')
        ax_tilt.set_xlabel('Tempo (amostras)')
        fig_tilt.tight_layout()
        tilt_path = f"tilt_grafico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        fig_tilt.savefig(tilt_path)
        plt.close(fig_tilt)
        paths.append(tilt_path)
    if show_vib and vibracoes_all:
        fig_vib, ax_vib = plt.subplots(figsize=(6, 3))
        ax_vib.plot(list(range(len(vibracoes_all))), vibracoes_all, color='#FFB266', linewidth=2)
        ax_vib.set_ylim(0, 5)
        ax_vib.set_title('Vibração (g) por tempo', color=COR_LARANJA, fontsize=12, fontweight='bold')
        ax_vib.set_ylabel('g')
        ax_vib.set_xlabel('Tempo (amostras)')
        fig_vib.tight_layout()
        vib_path = f"vib_grafico_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        fig_vib.savefig(vib_path)
        plt.close(fig_vib)
        paths.append(vib_path)
    return paths

grafico_tilt_var.trace_add('write', lambda *a: update_graph())
grafico_vib_var.trace_add('write', lambda *a: update_graph())

btn_frame = ctk.CTkFrame(frame_esquerdo, fg_color='transparent')
btn_frame.pack(pady=(10, 0))

# Inputs de limites
frame_limites = ctk.CTkFrame(frame_esquerdo, fg_color='transparent')
frame_limites.pack(fill='x', pady=(10, 0))

entry_tilt_limit = None
entry_vib_limit = None
label_tilt = None
label_vib = None
label_nenhum = None

def pode_iniciar():
    if not grafico_tilt_var.get() and not grafico_vib_var.get():
        return False
    if grafico_tilt_var.get():
        if not entry_tilt_limit or not entry_tilt_limit.get().strip():
            return False
        try:
            float(entry_tilt_limit.get())
        except:
            return False
    if grafico_vib_var.get():
        if not entry_vib_limit or not entry_vib_limit.get().strip():
            return False
        try:
            float(entry_vib_limit.get())
        except:
            return False
    return True

def atualizar_estado_iniciar(*args):
    if pode_iniciar():
        btn_start.configure(state='normal')
    else:
        btn_start.configure(state='disabled')

def atualizar_inputs_limites():
    global entry_tilt_limit, entry_vib_limit, label_tilt, label_vib, label_nenhum
    for widget in frame_limites.winfo_children():
        widget.destroy()
    entry_tilt_limit = None
    entry_vib_limit = None
    label_tilt = None
    label_vib = None
    label_nenhum = None
    if grafico_tilt_var.get():
        label_tilt = ctk.CTkLabel(frame_limites, text="Limite de inclinação:", font=('Segoe UI', 12))
        label_tilt.pack(pady=(0, 2))
        entry_tilt_limit = ctk.CTkEntry(frame_limites, width=60)
        entry_tilt_limit.insert(0, "80.0")
        entry_tilt_limit.pack(pady=(0, 8))
        entry_tilt_limit.bind('<KeyRelease>', lambda e: atualizar_estado_iniciar())
    if grafico_vib_var.get():
        label_vib = ctk.CTkLabel(frame_limites, text="Limite de vibração:", font=('Segoe UI', 12))
        label_vib.pack(pady=(0, 2))
        entry_vib_limit = ctk.CTkEntry(frame_limites, width=60)
        entry_vib_limit.insert(0, "1.5")
        entry_vib_limit.pack(pady=(0, 8))
        entry_vib_limit.bind('<KeyRelease>', lambda e: atualizar_estado_iniciar())
    if not grafico_tilt_var.get() and not grafico_vib_var.get():
        label_nenhum = ctk.CTkLabel(frame_limites, text="Nenhum gráfico selecionado", font=('Segoe UI', 12, 'italic'), text_color=COR_LARANJA)
        label_nenhum.pack(pady=10)
    atualizar_estado_iniciar()

grafico_tilt_var.trace_add('write', lambda *a: atualizar_estado_iniciar())
grafico_vib_var.trace_add('write', lambda *a: atualizar_estado_iniciar())

btn_start = ctk.CTkButton(
    frame_esquerdo, text='Iniciar',
    fg_color=COR_LARANJA, hover_color='#FFB266',
    text_color=COR_PRETO, font=('Segoe UI', 14, 'bold'),
    width=140, height=40, corner_radius=10,
    command=lambda: start_recepcao(),
    state='disabled'
)
btn_start.pack(side='bottom', pady=20)

def setup_inputs_iniciais():
    atualizar_inputs_limites()
setup_inputs_iniciais()

# Lado direito
frame_passos = ctk.CTkFrame(frame_direito, fg_color='transparent')
frame_passos.pack(fill='both', expand=True)
label_passos = ctk.CTkLabel(
    frame_passos,
    text=(
        'Como usar o Riggy:\n'
        '1. Selecione os gráficos desejados à esquerda.\n'
        '2. Defina os limites para cada gráfico selecionado.\n'
        '3. Clique em Iniciar para começar a receber dados.\n'
        '4. Clique em Encerrar para parar a coleta.\n'
        '5. Gere o relatório com PDF e vídeo anexado.'
    ),
    font=('Segoe UI', 15),
    justify='left',
    text_color=COR_TEXTO
)
label_passos.pack(padx=30, pady=30, anchor='center')

frame_graficos = ctk.CTkFrame(frame_direito, fg_color='transparent')
canvas.get_tk_widget().pack(fill='both', expand=True, pady=(0, 10))

frame_botoes = ctk.CTkFrame(frame_graficos, fg_color='transparent')
frame_botoes.pack(fill='x', pady=(10, 10))

btn_encerrar = ctk.CTkButton(
    frame_botoes, text='Encerrar',
    fg_color=COR_LARANJA, hover_color='#FFB266',
    text_color=COR_PRETO, font=('Segoe UI', 14, 'bold'),
    width=140, height=40, corner_radius=10,
    command=lambda: stop_recepcao(),
    state='disabled'
)
btn_encerrar.pack(side='left', padx=10)

btn_report = ctk.CTkButton(
    frame_botoes, text='Gerar relatório',
    fg_color=COR_LARANJA, hover_color='#FFB266',
    text_color=COR_PRETO, font=('Segoe UI', 14, 'bold'),
    width=140, height=40, corner_radius=10,
    command=gerar_relatorio, state='disabled'
)
btn_report.pack(side='left', padx=10)

def atualizar_lado_direito(estado):
    if estado == 'passos':
        frame_graficos.pack_forget()
        frame_passos.pack(fill='both', expand=True)
    elif estado == 'graficos':
        frame_passos.pack_forget()
        frame_graficos.pack(fill='both', expand=True)
        btn_encerrar.configure(state='normal')
        btn_report.configure(state='disabled')
    elif estado == 'encerrado':
        frame_passos.pack_forget()
        frame_graficos.pack(fill='both', expand=True)
        btn_encerrar.configure(state='disabled')
        btn_report.configure(state='normal')

atualizar_lado_direito('passos')

def start_recepcao():
    global running, thread, TILT_THRESHOLD, VIB_THRESHOLD, encerrado
    reset_dados()
    
    # Inicia a gravação de vídeo
    iniciar_gravacao()
    
    try:
        if grafico_tilt_var.get() and entry_tilt_limit:
            TILT_THRESHOLD = float(entry_tilt_limit.get())
    except:
        TILT_THRESHOLD = 80.0
    try:
        if grafico_vib_var.get() and entry_vib_limit:
            VIB_THRESHOLD = float(entry_vib_limit.get())
    except:
        VIB_THRESHOLD = 1.5
    
    running = True
    encerrado = False
    status_label.configure(text='Recebendo...', text_color=COR_LARANJA)
    btn_start.configure(state='disabled')
    atualizar_lado_direito('graficos')
    thread = threading.Thread(target=servidor_udp, daemon=True)
    thread.start()
    update_graph()

def reset_dados():
    global tempo, tilts, vibracoes, alerts, t, gravity, tilt_alerted, vib_alerted, tilts_all, vibracoes_all
    tempo = []
    tilts = deque(maxlen=WINDOW_SIZE)
    vibracoes = deque(maxlen=WINDOW_SIZE)
    alerts = []
    t = 0
    gravity = [0.0, 0.0, 9.81]
    tilt_alerted = False
    vib_alerted = False
    tilts_all = []
    vibracoes_all = []

def stop_recepcao():
    global running, encerrado
    running = False
    encerrado = True
    status_label.configure(text='Parado', text_color=COR_LARANJA)
    btn_start.configure(state='normal')
    atualizar_lado_direito('encerrado')
    update_graph()

app.mainloop()
