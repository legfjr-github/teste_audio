import streamlit as st
from spleeter.separator import Separator
import os
import tempfile
import gc  # Importamos o Garbage Collector para limpar memória na marra

# Configuração da página para evitar recarregamentos desnecessários
st.set_page_config(page_title="Separador de Áudio", layout="centered")

st.title("Separador de Áudio IA (Versão Leve) 🎵")
st.write("Faça upload de uma música para separar voz e instrumentos.")

st.sidebar.header("Configurações")
# Opção para limitar a duração e economizar RAM
duracao_max = st.sidebar.slider("Limitar duração (segundos)", 30, 300, 60, help="Diminua se o app travar.")
stems = st.sidebar.selectbox("Tipo de separação", ["2 stems (Voz + Música)"]) # Removi 4 stems pois é muito pesado pro free tier

# Função para carregar o modelo
@st.cache_resource
def load_separator():
    # O SEGREDO ESTÁ AQUI: multiprocess=False
    # Isso impede que o Spleeter crie subprocessos que estouram a RAM do Streamlit
    return Separator('spleeter:2stems', multiprocess=False)

try:
    separator = load_separator()
    st.success("Modelo IA carregado em modo de economia de memória!")
except Exception as e:
    st.error(f"Erro ao carregar modelo: {e}")

uploaded_file = st.file_uploader("Escolha um arquivo mp3/wav/m4a", type=["mp3", "wav", "m4a"])

if uploaded_file is not None:
    if st.button("Separar Áudio"):
        # Barra de progresso para feedback visual
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            with st.spinner('Processando... (Isso usa muita CPU, aguarde)'):
                status_text.text("Preparando arquivos...")
                
                # Limpeza de memória antes de começar
                gc.collect()

                with tempfile.TemporaryDirectory() as temp_dir:
                    # Salva arquivo de entrada
                    temp_audio_path = os.path.join(temp_dir, "input_audio")
                    with open(temp_audio_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    status_text.text("Separando faixas com IA...")
                    progress_bar.progress(30)
                    
                    # Executa a separação
                    # Adicionei o parametro 'duration' controlado pelo slider
                    separator.separate_to_file(
                        temp_audio_path, 
                        temp_dir, 
                        codec='mp3', 
                        bitrate='128k',
                        duration=duracao_max
                    )
                    
                    progress_bar.progress(80)
                    status_text.text("Finalizando...")

                    # Caminhos dos arquivos gerados
                    output_folder = os.path.join(temp_dir, "input_audio")
                    path_vocals = os.path.join(output_folder, "vocals.mp3")
                    path_music = os.path.join(output_folder, "accompaniment.mp3")

                    st.write("---")
                    col1, col2 = st.columns(2)
                    
                    # Exibe resultados
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
            st.warning("Se o app reiniciou, o arquivo era muito pesado para o servidor gratuito.")
        
        finally:
            # Limpeza final de memória
            gc.collect()
