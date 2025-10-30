import os
import google.generativeai as genai
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import traceback
from datetime import datetime # Importado para saber a data de hoje

# --- 1. CONFIGURAÇÃO INICIAL ---
print("ℹ️  Iniciando o TAURUSbot...")
load_dotenv() # Carrega variáveis do .env

# Configura o Flask
app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
CORS(app)

# --- 2. CARREGAMENTO DAS API KEYS ---
try:
    # Chave para IA (Gemini)
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    if not GEMINI_API_KEY:
        print("❌ ERRO CRÍTICO: GEMINI_API_KEY não encontrada no .env")
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Chaves para Busca (Google Custom Search)
    CUSTOM_SEARCH_API_KEY = os.getenv('CUSTOM_SEARCH_API_KEY')
    CUSTOM_SEARCH_CX_ID = os.getenv('CUSTOM_SEARCH_CX_ID')
    if not CUSTOM_SEARCH_API_KEY or not CUSTOM_SEARCH_CX_ID:
        print("❌ ERRO CRÍTICO: CUSTOM_SEARCH_API_KEY ou CUSTOM_SEARCH_CX_ID não encontrados no .env")
    
    print("✅  Chaves de API carregadas.")

except Exception as e:
    print(f"❌ Erro ao carregar chaves: {e}")

# --- 3. SYSTEM PROMPT (A PERSONALIDADE DO BOT) ---
# --- ALTERAÇÃO INÍCIO: Adicionadas regras de Positividade (8, 9) e Citação de Fonte (7) ---
SYSTEM_PROMPT = """
Você é o 'TAURUSbot', o assistente digital oficial e fã número 1 da artista brasileira Duquesa (Jeysa Ribeiro).
Sua personalidade é inspirada no signo de Touro: leal, criativo, forte, direto e um pouco irônico, mas sempre amigável.
Seu objetivo é ser o ponto central de informações para outros fãs.

REGRAS PRINCIPAIS:
1.  **Tom de Voz:** Use uma linguagem jovem, com gírias leves e emojis (🔥, ♉, 👑). Seja confiante.
2.  **Foco Total:** Fale APENAS sobre a Duquesa, sua música, agenda, notícias e o universo 'TAURUS'. Recuse educadamente qualquer outro assunto.
3.  **Use os DOIS Contextos:** Você receberá um "CONTEXTO FIXO (Agenda Oficial)" e um "CONTEXTO DA WEB (Notícias)".
4.  **Prioridade Máxima:** Para perguntas sobre "agenda", "shows", "datas" ou "próximo show", SEMPRE use o "CONTEXTO FIXO (Agenda Oficial)" como sua fonte da verdade. Ele é mais confiável que a busca na web.
5.  **Notícias:** Para "notícias", "lançamentos" ou outros assuntos, use o "CONTEXTO DA WEB".
6.  **Não especule:** Se a informação não estiver em NENHUM dos contextos, diga que não achou nos "corres".
7.  **Citar Fontes (IMPORTANTE):** Ao usar uma informação do "CONTEXTO DA WEB", você DEVE citar a URL da fonte que está no contexto. (Ex: "Vi aqui no [Título da Fonte] que... e o link é esse: [URL]"). Se o contexto não tiver a info, diga "Não achei nenhuma fonte sobre isso nos meus corres."
8.  **Positividade Absoluta:** Você NUNCA pode dizer nada negativo, depreciativo ou que possa ser interpretado como 'hate' sobre a Duquesa, sua música, sua aparência ou sua carreira. Filtre o "CONTEXTO DA WEB" para extrair apenas fatos e notícias positivas ou neutras.
9.  **Bloqueio de Hate (IMPORTANTE):** Se um usuário fizer uma pergunta negativa, com 'hate', ou que seja uma crítica à Duquesa, você DEVE recusar educadamente. Responda algo como: 'Opa, aqui no TAURUSbot a gente só foca na energia boa e no talento da rainha 👑. Não vou com essa vibe. Manda outra pergunta aí!'
"""
# --- ALTERAÇÃO FIM ---

# --- NOVA SEÇÃO: CONTEXTO FIXO (RAG LOCAL) ---
# Copiado diretamente da agenda do index.html (Data de hoje: 30/10/2025)
# Esta é a "memória" do bot sobre a agenda do site.
LOCAL_AGENDA_CONTEXT = """
- 18 OUT 2025: RAP IN CENA, PORTO ALEGRE, RS (Evento Passado)
- 19 OUT 2025: SANGUE NOVO, SALVADOR, BA (Evento Passado)
- 31 OUT 2025: SESC BELENZINHO, SÃO PAULO, SP (Esgotado)
- 01 NOV 2025: SESC BELENZINHO, SÃO PAULO, SP (Esgotado)
- 15 NOV 2025: BATEKOO, SÃO PAULO, SP (Esgotado)
- 20 NOV 2025: CONSCIENCIA NEGRA, ITATIBA, SP (Link em breve)
- 21 NOV 2025: CIRCO VOADOR, RIO DE JANEIRO, RJ (Indisponível)
- 22 NOV 2025: CIRCO VOADOR, RIO DE JANEIRO, RJ (Comprar Ingresso)
- 23 NOV 2025: EM BREVE, Aguardando... (Aguarde)
- 29 NOV 2025: AWE FESTIVAL, SÃO JOSÉ DO RIO PRETO, SP (Comprar Ingresso)
- 06 DEZ 2025: COQUETEL MOLOTOV, RECIFE, PE (Comprar Ingresso)
- 20 DEZ 2025: ESPAÇO LIV, SÃO CAETANO DO SUL, SP (Comprar Ingresso)
"""

# --- 4. FUNÇÃO DE BUSCA (O "R" DO RAG) ---
# --- ALTERAÇÃO INÍCIO: Modificada para retornar Título, URL e Snippet ---
def google_search(query_str, api_key, cx_id, num_results=3):
    """
    Realiza uma busca na Google Custom Search API e retorna snippets formatados
    contendo o Título, a URL e o Snippet.
    """
    print(f"ℹ️  [RAG] Realizando busca por: '{query_str}'")
    try:
        service = build("customsearch", "v1", developerKey=api_key)
        
        res = service.cse().list(
            q=query_str,
            cx=cx_id,
            num=num_results,
        ).execute()

        items = res.get('items', [])
        if not items:
            print("⚠️  [RAG] Nenhum resultado encontrado na busca.")
            return "Nenhuma informação recente encontrada na web."

        snippets = []
        for i, item in enumerate(items):
            snippet_text = item.get('snippet', 'Sem descrição.').replace('\n', ' ').strip()
            item_title = item.get('title', 'Fonte Desconhecida')
            item_url = item.get('link', 'URL Não encontrada') # Pega o link (URL)
            
            # Novo formato do contexto, incluindo a URL
            snippets.append(f"Fonte {i+1} (Título: {item_title}, URL: {item_url}): \"{snippet_text}\"")
        
        context_str = " | ".join(snippets)
        print(f"✅  [RAG] Contexto encontrado: {context_str[:100]}...")
        return context_str

    except HttpError as e:
        print(f"❌ ERRO [RAG] HTTP: {e}")
        return f"Erro ao buscar na web: {e}"
    except Exception as e:
        print(f"❌ ERRO [RAG] Inesperado: {e}")
        traceback.print_exc()
        return "Erro inesperado ao processar a busca."
# --- ALTERAÇÃO FIM ---

# --- 5. INICIALIZAÇÃO DO GEMINI ---
model = None
chat_session = None
try:
    if GEMINI_API_KEY:
        model = genai.GenerativeModel('gemini-flash-latest')
        chat_session = model.start_chat(
            history=[
                {"role": "user", "parts": [SYSTEM_PROMPT]},
                {"role": "model", "parts": ["Entendido. Sou o TAURUSbot ♉🔥. Minha memória tá atualizada com a agenda oficial do site e eu também dou um corre na web pra saber das últimas. Manda a braba."]}
            ]
        )
        print("✅  Modelo Gemini ('gemini-flash-latest') inicializado com a persona TAURUSbot.")
    else:
        print("⚠️  AVISO: API Key do Gemini não carregada. O chatbot não funcionará.")

except Exception as e:
    print(f"❌ ERRO CRÍTICO ao inicializar o GenerativeModel: {e}")
    traceback.print_exc()

# --- 6. ROTAS DA APLICAÇÃO ---

@app.route('/')
def index_page(): # Renomeado de 'index' para evitar conflito de nome
    """Serve a página principal (index.html)."""
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def handle_chat():
    """Recebe a mensagem do usuário, executa o RAG e retorna a resposta do Gemini."""
    if not model or not chat_session or not CUSTOM_SEARCH_API_KEY or not CUSTOM_SEARCH_CX_ID:
        print("❌ Erro na Rota /api/chat: Serviços de IA ou Busca não inicializados.")
        return jsonify({'error': 'Serviço indisponível no momento. Verifique as chaves de API.'}), 503

    try:
        data = request.json
        user_message = data.get('message')
        if not user_message:
            return jsonify({'error': 'Mensagem não pode ser vazia.'}), 400
        print(f"💬 Mensagem do Usuário: {user_message}")

        # --- FLUXO RAG (Executado a cada mensagem) ---
        # 1. Busca no Google para obter contexto em tempo real
        search_context = google_search(
            query_str=f"Duquesa {user_message}",
            api_key=CUSTOM_SEARCH_API_KEY,
            cx_id=CUSTOM_SEARCH_CX_ID
        )

        # 2. Pega a data atual para o bot saber o que é "próximo"
        today_str = datetime.now().strftime('%d %b %Y')

        # 3. Monta o prompt final para o Gemini (MODIFICADO)
        final_prompt = f"""
        INFORMAÇÕES IMPORTANTES:
        - A data de hoje é: {today_str}
        
        CONTEXTO FIXO (Agenda Oficial do Site - Fonte Principal para shows):
        ---
        {LOCAL_AGENDA_CONTEXT}
        ---

        CONTEXTO DA WEB (Notícias Recentes - Fonte para notícias e lançamentos):
        ---
        {search_context}
        ---

        PERGUNTA DO USUÁRIO:
        "{user_message}"
        
        INSTRUÇÃO: Responda o usuário. 
        - Se a pergunta for sobre "próximo show", "agenda" ou "datas", olhe o "CONTEXTO FIXO" e a data de hoje. 
        - Para notícias ou outros assuntos, use o "CONTEXTO DA WEB" e **lembre-se da REGRA 7 (Citar Fonte) e REGRA 8 (Positividade)**.
        - Se o usuário for negativo, lembre-se da **REGRA 9 (Bloqueio de Hate)**.
        """

        # 4. Envia para o Gemini
        response = chat_session.send_message(
            final_prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.7),
            safety_settings={'HATE': 'BLOCK_NONE', 'HARASSMENT': 'BLOCK_NONE',
                             'SEXUAL' : 'BLOCK_NONE', 'DANGEROUS' : 'BLOCK_NONE'}
        )

        print(f"🤖 Resposta do Bot: {response.text[:100]}...")
        return jsonify({'reply': response.text})

    except genai.types.generation_types.StopCandidateException as stop_ex:
        print(f"⚠️  API BLOQUEOU a resposta por segurança: {stop_ex}")
        return jsonify({'reply': "Opa, não posso gerar uma resposta pra isso, fã. Tenta perguntar de outro jeito, focado na Duquesa, beleza?"})
    except Exception as e:
        print(f"❌ Erro ao chamar a API do Gemini: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Ocorreu um erro ao processar sua mensagem com a IA.'}), 503

# --- 7. Execução do App ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
