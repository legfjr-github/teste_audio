import streamlit as st
from spleeter.separator import Separator
import shutil
import os
import tempfile

# Título da Página
st.title("Separador de Áudio com IA 🎵")
st.write("Faça upload de uma música para separar voz e instrumentos.")

# Configuração da Barra Lateral
st.sidebar.header("Configurações")
stems = st.sidebar.selectbox("Tipo de separação", ["2 stems (Voz + Música)", "4 stems (Voz, Baixo, Bateria, Outros)"])
stem_name = "spleeter:2stems" if "2" in stems else "spleeter:4stems"

# Função para carregar o modelo (Cache para não recarregar a cada clique)
@st.cache_resource
def load_separator(name):
    return Separator(name)

# Carrega o modelo
try:
    separator = load_separator(stem_name)
    st.success("Modelo de IA carregado e pronto!")
except Exception as e:
    st.error(f"Erro ao carregar modelo: {e}")

# Upload do Arquivo
uploaded_file = st.file_uploader("Escolha um arquivo mp3, wav ou m4a", type=["mp3", "wav", "m4a"])

if uploaded_file is not None:
    # Botão para processar
    if st.button("Separar Áudio"):
        with st.spinner('Processando... Isso pode levar alguns minutos.'):
            try:
                # 1. Cria diretório temporário
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Salva o arquivo enviado no disco temporário
                    temp_audio_path = os.path.join(temp_dir, "input_audio")
                    with open(temp_audio_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    # 2. Executa a separação
                    separator.separate_to_file(temp_audio_path, temp_dir, codec='mp3', bitrate='128k')
                    
                    # 3. Localiza os arquivos gerados
                    # O Spleeter cria uma subpasta com o nome do arquivo (neste caso "input_audio")
                    output_folder = os.path.join(temp_dir, "input_audio")
                    
                    path_vocals = os.path.join(output_folder, "vocals.mp3")
                    path_music = os.path.join(output_folder, "accompaniment.mp3")

                    # 4. Mostra os players e botões de download
                    st.write("---")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("🎤 Apenas Voz")
                        st.audio(path_vocals)
                        with open(path_vocals, "rb") as f:
                            st.download_button("Baixar Voz", f, file_name="voz_separada.mp3")
                            
                    with col2:
                        st.subheader("🎸 Apenas Música")
                        st.audio(path_music)
                        with open(path_music, "rb") as f:
                            st.download_button("Baixar Playback", f, file_name="playback_separado.mp3")
                            
                    st.success("Processamento concluído!")

            except Exception as e:
                st.error(f"Ocorreu um erro: {e}")
                st.info("Dica: Se for erro de memória, tente um áudio mais curto.")
