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

st.set_page_config(page_title="Studio AI: Youtube & Upload", layout="centered")

st.title("Studio de Áudio & Vídeo IA 🎥🎵")
st.write("Baixe vídeos, converta mp3 ou separe voz e instrumentos (IA).")

# --- GERENCIAMENTO DE ESTADO (SESSION STATE) ---
if 'yt_info' not in st.session_state: st.session_state.yt_info = None
if 'processed' not in st.session_state: st.session_state.processed = False
# Caminhos para download
vars_path = ['path_voz', 'path_music', 'path_zip', 'path_video_download', 'path_audio_download']
for v in vars_path:
    if v not in st.session_state: st.session_state[v] = None

# --- FUNÇÕES DE UTILIDADE ---
def limpar_memoria():
    gc.collect()

def resetar_sessao(keep_yt_info=False):
    """Limpa arquivos processados anteriormente"""
    keys_to_clear = ['path_voz', 'path_music', 'path_zip', 'path_video_download', 'path_audio_download', 'processed']
    for key in keys_to_clear:
        if key in st.session_state:
            st.session_state[key] = None
    
    if not keep_yt_info:
        st.session_state.yt_info = None
    
    limpar_memoria()

def ler_arquivo(path):
    """Lê arquivo em bytes para download (Evita manter na RAM o tempo todo)"""
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None

# --- CARREGAMENTO DO MODELO IA ---
@st.cache_resource
def load_separator():
    return Separator('spleeter:2stems-16kHz', multiprocess=False)

try:
    separator = load_separator()
except Exception as e:
    st.error(f"Erro ao carregar IA: {e}")

# --- BARRA LATERAL (CONFIGURAÇÕES) ---
st.sidebar.header("⚙️ Configurações de Áudio (IA)")
chunk_len_sec = st.sidebar.slider("Tamanho do Bloco (seg)", 30, 60, 60)
crossfade_ms = st.sidebar.slider("Suavização/Overlap (ms)", 0, 3000, 1000)
aplicar_norm = st.sidebar.checkbox("Normalizar & Filtrar", value=True)

# --- FUNÇÃO PRINCIPAL DE PROCESSAMENTO (IA) ---
def processar_separacao_audio(source_path, status_placeholder, progress_bar):
    """
    Função reutilizável que recebe um caminho de áudio (Upload ou YouTube)
    e executa o Spleeter com chunking e overlap.
    """
    try:
        # Cria diretório temporário para esta sessão
        session_temp_dir = tempfile.mkdtemp()
        
        status_placeholder.text("Lendo áudio original...")
        original_audio = AudioSegment.from_file(source_path)
        
        # Parâmetros de corte
        step_ms = chunk_len_sec * 1000
        chunk_total_ms = step_ms + crossfade_ms
        starts = range(0, len(original_audio), step_ms)
        total_chunks = len(starts)
        
        combined_vocals = AudioSegment.empty()
        combined_music = AudioSegment.empty()

        for i, start_time in enumerate(starts):
            limpar_memoria()
            step_percent = int((i / total_chunks) * 80)
            progress_bar.progress(step_percent)
            status_placeholder.text(f"Processando IA: Parte {i+1}/{total_chunks}...")

            # Corta
            end_time = min(start_time + chunk_total_ms, len(original_audio))
            chunk = original_audio[start_time:end_time]
            
            # Salva temp
            chunk_path = os.path.join(session_temp_dir, f"temp_chunk.mp3")
            chunk.export(chunk_path, format="mp3")
            
            # Spleeter
            try:
                separator.separate_to_file(chunk_path, session_temp_dir, codec='mp3', bitrate='192k')
            except Exception as e:
                print(f"Erro chunk {i}: {e}")
                continue

            # Recupera e funde
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

        # Limpeza do original
        del original_audio
        limpar_memoria()

        status_placeholder.text("Finalizando e otimizando...")
        
        # Pós-processamento
        if aplicar_norm:
            combined_vocals = effects.normalize(combined_vocals)
            combined_music = effects.normalize(combined_music)
            combined_vocals = combined_vocals.high_pass_filter(80)

        # Salvando Finais
        final_voz_path = os.path.join(session_temp_dir, "voz_final.mp3")
        final_music_path = os.path.join(session_temp_dir, "playback_final.mp3")
        final_zip_path = os.path.join(session_temp_dir, "pacote_ia.zip")
        
        combined_vocals.export(final_voz_path, format="mp3", bitrate="192k")
        combined_music.export(final_music_path, format="mp3", bitrate="192k")
        
        with zipfile.ZipFile(final_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(final_voz_path, "voz.mp3")
            zf.write(final_music_path, "playback.mp3")
        
        # Atualiza Estado
        st.session_state.path_voz = final_voz_path
        st.session_state.path_music = final_music_path
        st.session_state.path_zip = final_zip_path
        st.session_state.processed = True
        
        progress_bar.progress(100)
        status_placeholder.text("Processamento Concluído!")
        
        # Cleanup final
        del combined_vocals
        del combined_music
        limpar_memoria()
        
    except Exception as e:
        st.error(f"Erro no processamento: {e}")
        limpar_memoria()

# --- FUNÇÕES YOUTUBE ---
def get_yt_info(url):
    ydl_opts = {
        'quiet': True, 
        'no_warnings': True,
        'format': 'best',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            return ydl.extract_info(url, download=False)
        except Exception as e:
            return None

def download_yt_content(url, mode, format_id=None):
    """Baixa Vídeo ou Áudio do YouTube"""
    temp_dir = tempfile.mkdtemp()
    
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'quiet': True,
    }

    if mode == 'audio_only' or mode == 'for_spleeter':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    elif mode == 'video':
        # Tenta baixar o formato pedido + melhor áudio e fazer merge
        if format_id:
             ydl_opts['format'] = f"{format_id}+bestaudio/best"
        else:
             ydl_opts['format'] = "bestvideo+bestaudio/best"
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        if mode == 'audio_only' or mode == 'for_spleeter':
            # yt-dlp muda extensão para mp3 no post-process
            filename = os.path.splitext(filename)[0] + ".mp3"
            
        return filename

# ================= INTERFACE =================

tab_upload, tab_youtube = st.tabs(["📂 Arquivo Local", "🔗 Link do YouTube"])

# --- TAB 1: UPLOAD DE ARQUIVO ---
with tab_upload:
    uploaded_file = st.file_uploader("Envie seu arquivo (mp3, wav, m4a)", type=["mp3", "wav", "m4a"])
    
    if uploaded_file is not None:
        if st.button("Separar Voz e Playback (Arquivo Local)"):
            resetar_sessao()
            # Salva o upload no disco para processar
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                tmp_file.write(uploaded_file.getbuffer())
                tmp_path = tmp_file.name
            
            prog_bar = st.progress(0)
            status_txt = st.empty()
            processar_separacao_audio(tmp_path, status_txt, prog_bar)
            st.rerun()

# --- TAB 2: YOUTUBE ---
with tab_youtube:
    yt_url = st.text_input("Cole o link do YouTube aqui:")
    
    if st.button("🔍 Analisar Link"):
        if yt_url:
            with st.spinner("Buscando informações do vídeo..."):
                info = get_yt_info(yt_url)
                if info:
                    st.session_state.yt_info = info
                    resetar_sessao(keep_yt_info=True) # Limpa downloads antigos mas mantém info
                else:
                    st.error("Não foi possível acessar o vídeo. Verifique o link.")
        else:
            st.warning("Cole um link primeiro.")

    # Se já analisou o link, mostra opções
    if st.session_state.yt_info:
        info = st.session_state.yt_info
        st.subheader(f"🎬 {info.get('title')}")
        st.image(info.get('thumbnail'), width=300)
        
        # Opções de Ação
        action = st.radio("O que deseja fazer?", 
                          ["Baixar Áudio (MP3)", "Baixar Vídeo (MP4)", "Separar Voz e Playback (IA)"])
        
        if action == "Baixar Vídeo (MP4)":
            # Filtra resoluções disponíveis (apenas mp4 para compatibilidade)
            formats = [f for f in info['formats'] if f.get('vcodec') != 'none']
            # Cria lista única de resoluções (height)
            resolutions = sorted(list(set([f.get('height') for f in formats if f.get('height')])), reverse=True)
            res_options = [f"{r}p" for r in resolutions if r]
            
            selected_res = st.selectbox("Escolha a Resolução:", res_options)
            
            if st.button("⬇️ Baixar Vídeo"):
                target_height = int(selected_res.replace('p', ''))
                # Acha o format_id para aquela altura (pega o primeiro que achar)
                fmt_id = next((f['format_id'] for f in formats if f.get('height') == target_height), None)
                
                with st.spinner("Baixando e convertendo vídeo (pode demorar)..."):
                    try:
                        v_path = download_yt_content(yt_url, 'video', fmt_id)
                        st.session_state.path_video_download = v_path
                        st.success("Vídeo pronto!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro no download: {e}")

        elif action == "Baixar Áudio (MP3)":
            if st.button("⬇️ Baixar MP3"):
                with st.spinner("Baixando áudio..."):
                    try:
                        a_path = download_yt_content(yt_url, 'audio_only')
                        st.session_state.path_audio_download = a_path
                        st.success("Áudio pronto!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

        elif action == "Separar Voz e Playback (IA)":
            st.info("Isso baixará o áudio do vídeo e aplicará a Inteligência Artificial.")
            if st.button("🚀 Iniciar Processo IA"):
                with st.spinner("Baixando áudio do YouTube para processamento..."):
                    try:
                        # 1. Baixa áudio temporário
                        temp_audio_path = download_yt_content(yt_url, 'for_spleeter')
                        
                        # 2. Chama a função de separação (mesma do upload)
                        prog_bar = st.progress(0)
                        status_txt = st.empty()
                        processar_separacao_audio(temp_audio_path, status_txt, prog_bar)
                        
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")


# ================= ÁREA DE DOWNLOADS (COMUM) =================
st.write("---")

# 1. Downloads da IA (Voz/Playback)
if st.session_state.processed:
    st.subheader("🎵 Resultados da IA")
    c1, c2, c3 = st.columns(3)
    try:
        with c1:
            st.download_button("🎤 Baixar Voz", data=ler_arquivo(st.session_state.path_voz), file_name="voz.mp3", mime="audio/mp3")
        with c2:
            st.download_button("🎸 Baixar Playback", data=ler_arquivo(st.session_state.path_music), file_name="playback.mp3", mime="audio/mp3")
        with c3:
            st.download_button("📦 Baixar ZIP", data=ler_arquivo(st.session_state.path_zip), file_name="pacote_ia.zip", mime="application/zip")
    except:
        st.error("Arquivos não encontrados. Tente processar novamente.")

# 2. Downloads do YouTube (Vídeo/Áudio direto)
if st.session_state.path_video_download:
    st.subheader("🎬 Vídeo Baixado")
    file_path = st.session_state.path_video_download
    file_name = os.path.basename(file_path)
    try:
        # Lê em chunks ou exibe vídeo
        st.video(file_path)
        st.download_button("💾 Salvar Vídeo no PC", data=ler_arquivo(file_path), file_name=file_name, mime="video/mp4")
    except:
        st.warning("Vídeo expirou.")

if st.session_state.path_audio_download:
    st.subheader("🎵 Áudio Baixado")
    file_path = st.session_state.path_audio_download
    file_name = os.path.basename(file_path)
    try:
        st.audio(file_path)
        st.download_button("💾 Salvar MP3 no PC", data=ler_arquivo(file_path), file_name=file_name, mime="audio/mp3")
    except:
        st.warning("Áudio expirou.")

# Botão de Reset Geral
if st.button("🧹 Limpar Tudo e Recomeçar"):
    resetar_sessao()
    st.rerun()
