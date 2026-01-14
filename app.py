import streamlit as st
from spleeter.separator import Separator
import os
import tempfile
import gc 

st.set_page_config(page_title="Separador de Áudio", layout="centered")

st.title("Separador de Áudio IA (Versão Leve) 🎵")
st.write("Faça upload de uma música para separar voz e instrumentos.")

st.sidebar.header("Configurações")
duracao_max = st.sidebar.slider("Limitar duração (segundos)", 30, 300, 60, help="Diminua se o app travar.")
stems = st.sidebar.selectbox("Tipo de separação", ["2 stems (Voz + Música)"]) 

@st.cache_resource
def load_separator():
    # multiprocess=False é crucial para não estourar a memória
    return Separator('spleeter:2stems', multiprocess=False)

try:
    separator = load_separator()
    st.success("Modelo IA carregado!")
except Exception as e:
    st.error(f"Erro ao carregar modelo: {e}")

uploaded_file = st.file_uploader("Escolha um arquivo mp3/wav/m4a", type=["mp3", "wav", "m4a"])

if uploaded_file is not None:
    if st.button("Separar Áudio"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            with st.spinner('Processando...'):
                gc.collect() # Limpa memória

                with tempfile.TemporaryDirectory() as temp_dir:
                    # --- MUDANÇA AQUI ---
                    # Damos um nome fixo com extensão .mp3 para evitar conflito de pasta
                    input_filename = "song.mp3"
                    temp_audio_path = os.path.join(temp_dir, input_filename)
                    
                    # Salva o arquivo
                    with open(temp_audio_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    status_text.text("Separando faixas...")
                    progress_bar.progress(30)
                    
                    # Executa a separação
                    separator.separate_to_file(
                        temp_audio_path, 
                        temp_dir, 
                        codec='mp3', 
                        bitrate='128k',
                        duration=duracao_max
                    )
                    
                    progress_bar.progress(80)
                    status_text.text("Finalizando...")

                    # --- AJUSTE NOS CAMINHOS ---
                    # O Spleeter cria uma pasta com o nome do arquivo (sem extensão)
                    # Como o arquivo chama "song.mp3", a pasta será "song"
                    output_folder = os.path.join(temp_dir, "song")
                    
                    path_vocals = os.path.join(output_folder, "vocals.mp3")
                    path_music = os.path.join(output_folder, "accompaniment.mp3")

                    st.write("---")
                    col1, col2 = st.columns(2)
                    
                    # Verifica e exibe
                    if os.path.exists(path_vocals):
                        with col1:
                            st.subheader("🎤 Voz")
                            st.audio(path_vocals)
                            with open(path_vocals, "rb") as f:
                                st.download_button("Baixar Voz", f, file_name="voz.mp3")
                    
                    if os.path.exists(path_music):
                        with col2:
                            st.subheader("🎸 Música")
                            st.audio(path_music)
                            with open(path_music, "rb") as f:
                                st.download_button("Baixar Playback", f, file_name="playback.mp3")
                    
                    progress_bar.progress(100)
                    st.success("Sucesso!")
                    
        except Exception as e:
            st.error(f"Ocorreu um erro: {e}")
        
        finally:
            gc.collect()
