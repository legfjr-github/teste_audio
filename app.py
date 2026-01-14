import streamlit as st
from spleeter.separator import Separator
import os
import tempfile
import gc
from pydub import AudioSegment
import shutil
from io import BytesIO
import zipfile  # <--- Biblioteca para criar o ZIP

# --- CONFIGURAÇÃO INICIAL ---
path_to_ffmpeg = shutil.which("ffmpeg") 
path_to_ffprobe = shutil.which("ffprobe")

if path_to_ffmpeg:
    AudioSegment.converter = path_to_ffmpeg
if path_to_ffprobe:
    AudioSegment.ffprobe = path_to_ffprobe

st.set_page_config(page_title="Separador de Áudio", layout="centered")

st.title("Separador de Áudio (Modo Segmentado) ✂️")
st.write("Processa músicas longas e mantém os arquivos para download.")

# --- SESSION STATE (A MÁGICA PARA NÃO SUMIR) ---
if 'vocals_buffer' not in st.session_state:
    st.session_state.vocals_buffer = None
if 'music_buffer' not in st.session_state:
    st.session_state.music_buffer = None
if 'processed' not in st.session_state:
    st.session_state.processed = False

# Configurações
st.sidebar.header("Configurações")
chunk_len_sec = st.sidebar.slider("Tamanho do pedaço (seg)", 30, 60, 60)

@st.cache_resource
def load_separator():
    return Separator('spleeter:2stems', multiprocess=False)

try:
    separator = load_separator()
    st.success("IA carregada!")
except Exception as e:
    st.error(f"Erro IA: {e}")

uploaded_file = st.file_uploader("Escolha um arquivo mp3/wav/m4a", type=["mp3", "wav", "m4a"])

# --- BOTÃO DE PROCESSAMENTO ---
if uploaded_file is not None:
    # Só mostra o botão se ainda não tiver processado ou se quiser fazer de novo
    if st.button("Separar Áudio Completo"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            with st.spinner('Lendo arquivo...'):
                original_audio = AudioSegment.from_file(uploaded_file)
                chunk_length_ms = chunk_len_sec * 1000
                chunks = [original_audio[i:i + chunk_length_ms] for i in range(0, len(original_audio), chunk_length_ms)]
                total_chunks = len(chunks)
                
                combined_vocals = AudioSegment.empty()
                combined_music = AudioSegment.empty()

                with tempfile.TemporaryDirectory() as master_temp_dir:
                    for i, chunk in enumerate(chunks):
                        gc.collect()
                        step_percent = int((i / total_chunks) * 100)
                        progress_bar.progress(step_percent)
                        status_text.text(f"Processando parte {i+1}/{total_chunks}...")

                        chunk_filename = f"chunk_{i}.mp3"
                        chunk_path = os.path.join(master_temp_dir, chunk_filename)
                        chunk.export(chunk_path, format="mp3")
                        
                        try:
                            separator.separate_to_file(
                                chunk_path, 
                                master_temp_dir, 
                                codec='mp3', 
                                bitrate='128k'
                            )
                        except Exception as e:
                            print(f"Erro chunk {i}: {e}")
                            continue

                        chunk_folder = f"chunk_{i}"
                        out_path = os.path.join(master_temp_dir, chunk_folder)
                        v_path = os.path.join(out_path, "vocals.mp3")
                        m_path = os.path.join(out_path, "accompaniment.mp3")
                        
                        if os.path.exists(v_path):
                            combined_vocals += AudioSegment.from_mp3(v_path)
                        if os.path.exists(m_path):
                            combined_music += AudioSegment.from_mp3(m_path)
                
                status_text.text("Gerando arquivos finais...")
                progress_bar.progress(90)
                
                # --- SALVA NO SESSION STATE ---
                # Usamos BytesIO para guardar na memória RAM
                buf_v = BytesIO()
                combined_vocals.export(buf_v, format="mp3", bitrate="192k")
                st.session_state.vocals_buffer = buf_v.getvalue() # Salva os bytes
                
                buf_m = BytesIO()
                combined_music.export(buf_m, format="mp3", bitrate="192k")
                st.session_state.music_buffer = buf_m.getvalue() # Salva os bytes
                
                st.session_state.processed = True
                
                progress_bar.progress(100)
                status_text.text("Concluído!")
                # Força recarregar a página para exibir os botões de download
                st.rerun()

        except Exception as e:
            st.error(f"Erro: {e}")
        finally:
            gc.collect()

# --- ÁREA DE DOWNLOAD (FORA DO IF DO BOTÃO) ---
if st.session_state.processed:
    st.write("---")
    st.success("Áudio processado e pronto para download!")
    
    col1, col2, col3 = st.columns(3)
    
    # Botão 1: Voz
    with col1:
        st.subheader("🎤 Voz")
        st.audio(st.session_state.vocals_buffer, format='audio/mp3')
        st.download_button(
            label="Baixar Voz",
            data=st.session_state.vocals_buffer,
            file_name="voz_separada.mp3",
            mime="audio/mp3"
        )
        
    # Botão 2: Música
    with col2:
        st.subheader("🎸 Playback")
        st.audio(st.session_state.music_buffer, format='audio/mp3')
        st.download_button(
            label="Baixar Playback",
            data=st.session_state.music_buffer,
            file_name="playback_separado.mp3",
            mime="audio/mp3"
        )

    # Botão 3: ZIP (Tudo junto)
    with col3:
        st.subheader("📦 Pacote")
        
        # Cria o ZIP na memória
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, false) as zf:
            zf.writestr("voz.mp3", st.session_state.vocals_buffer)
            zf.writestr("playback.mp3", st.session_state.music_buffer)
        
        st.write("Baixar tudo de uma vez:")
        st.download_button(
            label="Baixar ZIP",
            data=zip_buffer.getvalue(),
            file_name="arquivos_separados.zip",
            mime="application/zip"
        )
    
    # Botão para limpar e começar de novo
    if st.button("Começar novo processo"):
        st.session_state.processed = False
        st.session_state.vocals_buffer = None
        st.session_state.music_buffer = None
        st.rerun()
