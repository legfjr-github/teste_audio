import streamlit as st
from spleeter.separator import Separator
import os
import tempfile
import gc
from pydub import AudioSegment, effects
import shutil
import zipfile
import yt_dlp

# --- CONFIGURAÇÃO INICIAL E CAMINHOS ---
path_to_ffmpeg = shutil.which("ffmpeg") 
path_to_ffprobe = shutil.which("ffprobe")
if path_to_ffmpeg: AudioSegment.converter = path_to_ffmpeg
if path_to_ffprobe: AudioSegment.ffprobe = path_to_ffprobe

st.set_page_config(page_title="Studio AI", layout="centered")

st.title("Studio de Áudio & Vídeo IA 🎥🎵")
st.write("Baixe vídeos, converta mp3 ou separe voz e instrumentos (IA).")

# --- GERENCIAMENTO DE ESTADO ---
if 'yt_info' not in st.session_state: st.session_state.yt_info = None
if 'processed' not in st.session_state: st.session_state.processed = False
vars_path = ['path_voz', 'path_music', 'path_zip', 'path_video_download', 'path_audio_download']
for v in vars_path:
    if v not in st.session_state: st.session_state[v] = None

# --- FUNÇÕES UTILITÁRIAS ---
def limpar_memoria():
    gc.collect()

def resetar_sessao(keep_yt_info=False):
    keys_to_clear = ['path_voz', 'path_music', 'path_zip', 'path_video_download', 'path_audio_download', 'processed']
    for key in keys_to_clear:
        if key in st.session_state:
            st.session_state[key] = None
    if not keep_yt_info:
        st.session_state.yt_info = None
    limpar_memoria()

def ler_arquivo(path):
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None

# --- CARREGAMENTO IA ---
@st.cache_resource
def load_separator():
    return Separator('spleeter:2stems-16kHz', multiprocess=False)

try:
    separator = load_separator()
except Exception as e:
    st.error(f"Erro IA: {e}")

# --- SIDEBAR ---
st.sidebar.header("⚙️ Configurações IA")
chunk_len_sec = st.sidebar.slider("Tamanho do Bloco (seg)", 30, 60, 60)
crossfade_ms = st.sidebar.slider("Overlap (ms)", 0, 3000, 1000)
aplicar_norm = st.sidebar.checkbox("Normalizar", value=True)

# --- PROCESSAMENTO IA (FUNÇÃO MANTIDA IGUAL) ---
def processar_separacao_audio(source_path, status_placeholder, progress_bar):
    try:
        session_temp_dir = tempfile.mkdtemp()
        status_placeholder.text("Lendo áudio...")
        original_audio = AudioSegment.from_file(source_path)
        
        step_ms = chunk_len_sec * 1000
        chunk_total_ms = step_ms + crossfade_ms
        starts = range(0, len(original_audio), step_ms)
        total_chunks = len(starts)
        
        combined_vocals = AudioSegment.empty()
        combined_music = AudioSegment.empty()

        for i, start_time in enumerate(starts):
            limpar_memoria()
            progress_bar.progress(int((i / total_chunks) * 80))
            status_placeholder.text(f"Processando parte {i+1}/{total_chunks}...")

            end_time = min(start_time + chunk_total_ms, len(original_audio))
            chunk = original_audio[start_time:end_time]
            
            chunk_path = os.path.join(session_temp_dir, f"temp_chunk.mp3")
            chunk.export(chunk_path, format="mp3")
            
            try:
                separator.separate_to_file(chunk_path, session_temp_dir, codec='mp3', bitrate='192k')
            except:
                continue

            out_path = os.path.join(session_temp_dir, "temp_chunk")
            v_path = os.path.join(out_path, "vocals.mp3")
            m_path = os.path.join(out_path, "accompaniment.mp3")
            
            if os.path.exists(v_path) and os.path.exists(m_path):
                seg_v = AudioSegment.from_mp3(v_path)
                seg_m = AudioSegment.from_mp3(m_path)
                
                if i == 0:
                    combined_vocals += seg_v
                    combined_music += seg_m
                else:
                    combined_vocals = combined_vocals.append(seg_v, crossfade=crossfade_ms)
                    combined_music = combined_music.append(seg_m, crossfade=crossfade_ms)

        del original_audio
        limpar_memoria()

        status_placeholder.text("Finalizando...")
        if aplicar_norm:
            combined_vocals = effects.normalize(combined_vocals)
            combined_music = effects.normalize(combined_music)
            combined_vocals = combined_vocals.high_pass_filter(80)

        final_voz_path = os.path.join(session_temp_dir, "voz_final.mp3")
        final_music_path = os.path.join(session_temp_dir, "playback_final.mp3")
        final_zip_path = os.path.join(session_temp_dir, "pacote_ia.zip")
        
        combined_vocals.export(final_voz_path, format="mp3", bitrate="192k")
        combined_music.export(final_music_path, format="mp3", bitrate="192k")
        
        with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(final_voz_path, "voz.mp3")
            zf.write(final_music_path, "playback.mp3")
        
        st.session_state.path_voz = final_voz_path
        st.session_state.path_music = final_music_path
        st.session_state.path_zip = final_zip_path
        st.session_state.processed = True
        
        progress_bar.progress(100)
        status_placeholder.text("Concluído!")
        del combined_vocals
        del combined_music
        limpar_memoria()
        
    except Exception as e:
        st.error(f"Erro: {e}")
        limpar_memoria()

# --- FUNÇÕES YOUTUBE CORRIGIDAS (AQUI ESTÁ O SEGREDO) ---
def get_common_ydl_opts():
    """Opções padrão para evitar bloqueios e exigir user-agent mobile"""
    return {
        'quiet': True, 
        'no_warnings': True,
        # Força usar cliente Android para evitar bloqueio SABR/Empty File
        'extractor_args': {'youtube': {'player_client': ['android', 'ios']}},
        'nocheckcertificate': True,
    }

def get_yt_info(url):
    opts = get_common_ydl_opts()
    opts['format'] = 'best'
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            return ydl.extract_info(url, download=False)
        except Exception as e:
            return None
def teste(url):
    import yt_dlp
    from concurrent.futures import ThreadPoolExecutor
    
    # --- CONFIGURAÇÕES ---
    # Lista de links das páginas que contêm os vídeos
    links = [
        f'{url}',
    ]
    
    MAX_RESOLUTION = 1080  # Valor desejado (1080, 720, 480, etc.)
    CONCURRENT_DOWNLOADS = 2  # Quantos vídeos baixar ao mesmo tempo
    
    def download_video(url):
        """
        Função para baixar um único vídeo com as restrições dadas.
        """
        filename = ''
        ydl_opts = {
            # 'format': Seleciona o melhor vídeo que tenha altura <= MAX_RESOLUTION
            # e junta com o melhor áudio disponível.
            'format': f'bestvideo[height<={MAX_RESOLUTION}]+bestaudio/best[height<={MAX_RESOLUTION}]',
    
            # Pasta de destino e nome do arquivo (Título.Extensão)
            'outtmpl': '%(title)s.%(ext)s',
    
            # Otimizações extras
            'quiet': False,
            'no_warnings': True,
            'merge_output_format': 'mp4', # Garante que o arquivo final seja .mp4
        }
    
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"[INICIANDO] {url}")
                filename = ydl.prepare_filename(info)
                ydl.download([url])
                print(f"[CONCLUÍDO] {url}")
        except Exception as e:
            print(f"[ERRO] Falha ao baixar {url}: {e}")
        return filename
    
    def main():
        print(f"Iniciando downloads (Máximo {CONCURRENT_DOWNLOADS} simultâneos)...")
    
        # Gerencia a fila de downloads com multithreading
        with ThreadPoolExecutor(max_workers=CONCURRENT_DOWNLOADS) as executor:
            executor.map(download_video, links)
    
        print("\nProcesso finalizado!")

def download_yt_content(url, mode, format_id=None):
    temp_dir = tempfile.mkdtemp()
    
    # Pega as opções anti-bloqueio
    ydl_opts = get_common_ydl_opts()
    
    # Define o template de saída
    ydl_opts['outtmpl'] = os.path.join(temp_dir, '%(title)s.%(ext)s')

    if mode == 'audio_only' or mode == 'for_spleeter':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    elif mode == 'video':
        if format_id:
             ydl_opts['format'] = f"{format_id}+bestaudio/best"
        else:
             ydl_opts['format'] = "bestvideo+bestaudio/best"
        # Garante que saia como mp4 para compatibilidade
        ydl_opts['merge_output_format'] = 'mp4' 
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        if mode == 'audio_only' or mode == 'for_spleeter':
            filename = os.path.splitext(filename)[0] + ".mp3"
        elif mode == 'video':
            # Se for vídeo, garante que pegamos o arquivo merged (.mp4)
            base, _ = os.path.splitext(filename)
            filename = base + ".mp4"
            
        return filename

# ================= INTERFACE =================

tab_upload, tab_youtube = st.tabs(["📂 Arquivo Local", "🔗 Link do YouTube"])

with tab_upload:
    uploaded_file = st.file_uploader("Envie seu arquivo", type=["mp3", "wav", "m4a"])
    if uploaded_file and st.button("Separar (Upload)"):
        resetar_sessao()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            tmp_path = tmp_file.name
        prog_bar = st.progress(0)
        status_txt = st.empty()
        processar_separacao_audio(tmp_path, status_txt, prog_bar)
        st.rerun()

with tab_youtube:
    yt_url = st.text_input("Link do YouTube:")
    if st.button("🔍 Analisar"):
        if yt_url:
            with st.spinner("Buscando..."):
                info = get_yt_info(yt_url)
                if info:
                    st.session_state.yt_info = info
                    resetar_sessao(keep_yt_info=True)
                else:
                    st.error("Erro ao buscar vídeo. Tente outro link.")
    
    if st.session_state.yt_info:
        info = st.session_state.yt_info
        st.subheader(info.get('title'))
        st.image(info.get('thumbnail'), width=300)
        
        action = st.radio("Ação:", ["Baixar Áudio", "Baixar Vídeo", "Separar Voz/Playback (IA)"])
        
        if action == "Baixar Vídeo":
            formats = [f for f in info['formats'] if f.get('vcodec') != 'none']
            resolutions = sorted(list(set([f.get('height') for f in formats if f.get('height')])), reverse=True)
            res_options = [f"{r}p" for r in resolutions if r]
            selected_res = st.selectbox("Resolução:", res_options)
            
            if st.button("⬇️ Baixar Vídeo"):
                target_height = int(selected_res.replace('p', ''))
                fmt_id = next((f['format_id'] for f in formats if f.get('height') == target_height), None)
                with st.spinner("Baixando..."):
                    try:
                        v_path = download_yt_content(yt_url, 'video', fmt_id)
                        v_path = teste(yt_url)
                        st.session_state.path_video_download = v_path
                        st.success("Pronto!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

        elif action == "Baixar Áudio":
            if st.button("⬇️ Baixar MP3"):
                with st.spinner("Baixando..."):
                    try:
                        a_path = download_yt_content(yt_url, 'audio_only')
                        st.session_state.path_audio_download = a_path
                        st.success("Pronto!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

        elif action == "Separar Voz/Playback (IA)":
            if st.button("🚀 Iniciar IA"):
                with st.spinner("Baixando e Processando..."):
                    try:
                        temp_audio_path = download_yt_content(yt_url, 'for_spleeter')
                        prog_bar = st.progress(0)
                        status_txt = st.empty()
                        processar_separacao_audio(temp_audio_path, status_txt, prog_bar)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

# ================= DOWNLOADS =================
st.write("---")
if st.session_state.processed:
    st.subheader("🎵 IA Resultados")
    c1, c2, c3 = st.columns(3)
    try:
        with c1: st.download_button("🎤 Voz", ler_arquivo(st.session_state.path_voz), "voz.mp3", "audio/mp3")
        with c2: st.download_button("🎸 Playback", ler_arquivo(st.session_state.path_music), "playback.mp3", "audio/mp3")
        with c3: st.download_button("📦 ZIP", ler_arquivo(st.session_state.path_zip), "ia.zip", "application/zip")
    except: pass

if st.session_state.path_video_download:
    st.subheader("🎬 Vídeo")
    path = st.session_state.path_video_download
    try:
        st.video(path)
        st.download_button("💾 Salvar", ler_arquivo(path), os.path.basename(path), "video/mp4")
    except: pass

if st.session_state.path_audio_download:
    st.subheader("🎵 Áudio")
    path = st.session_state.path_audio_download
    try:
        st.audio(path)
        st.download_button("💾 Salvar", ler_arquivo(path), os.path.basename(path), "audio/mp3")
    except: pass

if st.button("🧹 Limpar Tudo"):
    resetar_sessao()
    st.rerun()
