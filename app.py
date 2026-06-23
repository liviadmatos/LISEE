import os
import json
import random
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv
from flask_cors import CORS

# Carrega as variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# Habilita CORS de forma segura para o desenvolvimento e produção
CORS(app)

# Configura a conexão com o Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("As variáveis de ambiente SUPABASE_URL e SUPABASE_KEY precisam estar configuradas.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------------------------------------------------
# Decorador para exigir autenticação via token JWT do Supabase
# -------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"erro": "Token de acesso ausente ou inválido"}), 401
        
        token = auth_header.split(' ')[1]
        try:
            user_response = supabase.auth.get_user(token)
            request.user = user_response.user
        except Exception as e:
            return jsonify({"erro": "Falha na autenticação", "detalhes": str(e)}), 401
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------------
# Rotas de Autenticação
# -------------------------------------------------------------------
@app.route('/api/auth/register', methods=['POST'])
def register():
    """Registra um novo usuário usando a trigger automática do Supabase."""
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    nome = data.get('nome')
    perfil = data.get('perfil')

    if not all([email, password, nome, perfil]):
        return jsonify({"erro": "Campos obrigatórios: email, password, nome, perfil"}), 400
    
    if perfil not in ('Aluno', 'Professor'):
        return jsonify({"erro": "Perfil deve ser estritamente 'Aluno' ou 'Professor'"}), 400

    try:
        # Cria o usuário no Auth - a trigger vai criar na tabela usuarios
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "nome": nome,
                    "perfil": perfil
                }
            }
        })
        
        if not auth_response.user:
            return jsonify({"erro": "Não foi possível criar a credencial de autenticação."}), 400
            
        user_id = auth_response.user.id

        # Aguarda a trigger criar o registro (pequeno delay)
        time.sleep(0.5)

        # Verifica se o registro foi criado
        user_check = supabase.table("usuarios").select("*").eq("id_usuario", user_id).execute()
        if not user_check.data:
            # Fallback: insere manualmente se a trigger falhar
            supabase.table("usuarios").insert({
                "id_usuario": user_id,
                "nome": nome,
                "email": email,
                "perfil": perfil,
                "criado_em": datetime.utcnow().isoformat()
            }).execute()

        return jsonify({
            "mensagem": "Usuário criado com sucesso",
            "user_id": user_id
        }), 201
        
    except Exception as e:
        print(f"❌ Erro no registro: {str(e)}")
        return jsonify({"erro": "Erro ao registrar usuário", "detalhes": str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Autentica o usuário e retorna o Token JWT."""
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({"erro": "Email e senha são obrigatórios"}), 400

    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not auth_response.user:
            return jsonify({"erro": "Usuário não encontrado"}), 401
            
        # Verifica se o registro existe na tabela usuarios
        user_check = supabase.table("usuarios")\
            .select("id_usuario, perfil, nome")\
            .eq("id_usuario", auth_response.user.id)\
            .execute()
            
        if not user_check.data:
            # Tenta criar o registro manualmente (fallback)
            try:
                supabase.table("usuarios").insert({
                    "id_usuario": auth_response.user.id,
                    "nome": auth_response.user.email,
                    "email": auth_response.user.email,
                    "perfil": "Aluno",
                    "criado_em": datetime.utcnow().isoformat()
                }).execute()
            except Exception as e:
                print(f"⚠️ Falha ao criar registro fallback: {e}")
                return jsonify({
                    "erro": "Perfil não encontrado",
                    "detalhes": "Entre em contato com o suporte"
                }), 403
        
        return jsonify({
            "access_token": auth_response.session.access_token,
            "user_id": auth_response.user.id,
            "perfil": user_check.data[0]['perfil'] if user_check.data else "Aluno"
        }), 200
        
    except Exception as e:
        print(f"❌ Erro no login: {str(e)}")
        return jsonify({
            "erro": "Credenciais inválidas ou incorretas",
            "detalhes": str(e)
        }), 401

# -------------------------------------------------------------------
# Perfil do Usuário
# -------------------------------------------------------------------
@app.route('/api/user/profile', methods=['GET'])
@login_required
def get_profile():
    """Retorna os dados do perfil logado."""
    user_id = request.user.id
    try:
        response = supabase.table("usuarios").select("*").eq("id_usuario", user_id).execute()
        if response.data:
            return jsonify(response.data[0]), 200
        return jsonify({"erro": "Perfil de usuário não encontrado no banco de dados"}), 404
    except Exception as e:
        return jsonify({"erro": "Erro ao buscar perfil", "detalhes": str(e)}), 500

# -------------------------------------------------------------------
# Termos e Radicais (Morfologia e Relações)
# -------------------------------------------------------------------
@app.route('/api/terms', methods=['GET'])
def list_terms():
    """Lista termos biológicos e suas relações ou radicais isolados."""
    tipo = request.args.get('tipo')
    area = request.args.get('area')

    try:
        if tipo == 'radicais_isolados':
            rad_response = supabase.table("radicais").select("*").execute()
            return jsonify(rad_response.data), 200

        # Faz o Join relacional correto trazendo a árvore de radicais ordenada
        query = supabase.table("termos").select("*, termo_radicais(ordem, radicais(*))")
        if area:
            query = query.eq("area", area)
            
        termos_response = query.execute()
        return jsonify(termos_response.data), 200
    except Exception as e:
        return jsonify({"erro": "Erro ao listar os termos", "detalhes": str(e)}), 500

@app.route('/api/terms/<int:term_id>', methods=['GET'])
def get_term(term_id):
    """Busca um termo específico destrinchando seus radicais associados."""
    try:
        response = supabase.table("termos").select("*, termo_radicais(ordem, radicais(*))").eq("id_termo", term_id).execute()
        if response.data:
            return jsonify(response.data[0]), 200
        return jsonify({"erro": "Termo biológico não encontrado"}), 404
    except Exception as e:
        return jsonify({"erro": "Erro ao buscar termo", "detalhes": str(e)}), 500

@app.route('/api/radicais/<int:radical_id>/terms', methods=['GET'])
def get_terms_by_radical(radical_id):
    """Busca todas as palavras complexas que se utilizam de um radical específico."""
    try:
        associations = supabase.table("termo_radicais").select("termos(*)").eq("fk_radical", radical_id).execute()
        termos = [item['termos'] for item in associations.data if item.get('termos')]
        return jsonify(termos), 200
    except Exception as e:
        return jsonify({"erro": "Erro ao filtrar termos por radical", "detalhes": str(e)}), 500

# -------------------------------------------------------------------
# Gestão de Turmas
# -------------------------------------------------------------------
@app.route('/api/turmas', methods=['POST'])
@login_required
def criar_turma():
    """Cria uma turma acadêmica e gera um código alfanumérico único de acesso."""
    user_id = request.user.id
    try:
        user_profile = supabase.table("usuarios").select("perfil").eq("id_usuario", user_id).execute()
        if not user_profile.data or user_profile.data[0]['perfil'] != 'Professor':
            return jsonify({"erro": "Acesso negado. Apenas professores podem abrir turmas."}), 403

        data = request.get_json() or {}
        nome_turma = data.get('nome')
        if not nome_turma:
            return jsonify({"erro": "O nome da turma é obrigatório"}), 400

        # Algoritmo seguro para garantir código de turma único
        while True:
            codigo = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))
            colisao = supabase.table("turmas").select("id_turma").eq("codigo", codigo).execute()
            if not colisao.data:
                break

        new_turma = {
            "nome": nome_turma,
            "codigo": codigo,
            "fk_professor": user_id,
            "criado_em": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        }
        result = supabase.table("turmas").insert(new_turma).execute()
        return jsonify(result.data[0]), 201
    except Exception as e:
        return jsonify({"erro": "Erro ao gerar turma", "detalhes": str(e)}), 500

@app.route('/api/turmas', methods=['GET'])
@login_required
def listar_turmas():
    """Lista as turmas vinculadas ao usuário logado (Professor ou Aluno)."""
    user_id = request.user.id
    try:
        perfil_res = supabase.table("usuarios").select("perfil").eq("id_usuario", user_id).execute()
        if not perfil_res.data:
            return jsonify({"erro": "Usuário inválido"}), 404
            
        perfil = perfil_res.data[0]['perfil']

        if perfil == 'Professor':
            turmas = supabase.table("turmas").select("*").eq("fk_professor", user_id).execute()
        else:
            matriculas = supabase.table("usuario_turma").select("fk_turma").eq("fk_usuario", user_id).execute()
            turmas_ids = [m['fk_turma'] for m in matriculas.data]
            if turmas_ids:
                turmas = supabase.table("turmas").select("*").in_("id_turma", turmas_ids).execute()
            else:
                turmas = {"data": []}
                
        return jsonify(turmas.data), 200
    except Exception as e:
        return jsonify({"erro": "Erro ao listar turmas", "detalhes": str(e)}), 500

@app.route('/api/turmas/join', methods=['POST'])
@login_required
def ingressar_turma():
    """Matricula um aluno em uma turma por meio do código identificador."""
    user_id = request.user.id
    data = request.get_json() or {}
    codigo = data.get('codigo')
    
    if not codigo:
        return jsonify({"erro": "O código de acesso é obrigatório"}), 400

    try:
        turma = supabase.table("turmas").select("*").eq("codigo", codigo.upper()).execute()
        if not turma.data:
            return jsonify({"erro": "Nenhuma turma foi encontrada com este código"}), 404

        turma_id = turma.data[0]['id_turma']
        
        # Verifica duplicidade de matrícula
        exist = supabase.table("usuario_turma").select("*").eq("fk_usuario", user_id).eq("fk_turma", turma_id).execute()
        if exist.data:
            return jsonify({"mensagem": "Você já faz parte desta turma acadêmica"}), 200

        supabase.table("usuario_turma").insert({
            "fk_usuario": user_id,
            "fk_turma": turma_id,
            "pontuacao": 0,
            "data_ingresso": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        }).execute()
        
        return jsonify({"mensagem": "Matrícula realizada com sucesso"}), 201
    except Exception as e:
        return jsonify({"erro": "Erro ao ingressar na turma", "detalhes": str(e)}), 500

# -------------------------------------------------------------------
# Trilhas Acadêmicas
# -------------------------------------------------------------------
@app.route('/api/trilhas', methods=['POST'])
@login_required
def criar_trilha():
    """Gera um roteiro guiado de termos (Trilha) vinculando os IDs das palavras."""
    user_id = request.user.id
    data = request.get_json() or {}
    nome = data.get('nome')
    term_ids = data.get('termos')  # Lista de IDs de termos

    if not nome or not term_ids:
        return jsonify({"erro": "Nome do roteiro e IDs dos termos são obrigatórios"}), 400

    try:
        trilha_resp = supabase.table("trilhas").insert({
            "nome": nome,
            "fk_professor": user_id,
            "criado_em": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        }).execute()
        
        trilha_id = trilha_resp.data[0]['id_trilha']

        # Bulk insert (inserção em lote) para melhor performance relacional
        inserts_trilha = [{"fk_trilha": trilha_id, "fk_termo": tid} for tid in term_ids]
        supabase.table("trilha_termos").insert(inserts_trilha).execute()

        return jsonify({"mensagem": "Trilha pedagógica estruturada", "id_trilha": trilha_id}), 201
    except Exception as e:
        return jsonify({"erro": "Erro ao criar trilha", "detalhes": str(e)}), 500

# -------------------------------------------------------------------
# Mecânica dos Jogos (Montagem e Decifrador)
# -------------------------------------------------------------------
@app.route('/api/jogos/montagem/start', methods=['GET'])
@login_required
def iniciar_montagem():
    """Busca um termo (da trilha ou geral) e embaralha seus radicais para o jogo."""
    trilha_id = request.args.get('trilha_id')
    try:
        if trilha_id:
            termos_rel = supabase.table("trilha_termos").select("fk_termo").eq("fk_trilha", trilha_id).execute()
            if not termos_rel.data:
                return jsonify({"erro": "Esta trilha não possui termos configurados"}), 404
            term_ids = [t['fk_termo'] for t in termos_rel.data]
            termo_id = random.choice(term_ids)
        else:
            all_terms = supabase.table("termos").select("id_termo").execute()
            if not all_terms.data:
                return jsonify({"erro": "Nenhum termo disponível no momento"}), 404
            termo_id = random.choice(all_terms.data)['id_termo']

        termo_dados = supabase.table("termos").select("*, termo_radicais(ordem, radicais(*))").eq("id_termo", termo_id).execute()
        termo = termo_dados.data[0]

        radicais_opcoes = []
        for tr in termo['termo_radicais']:
            rad = tr['radicais']
            if rad:
                radicais_opcoes.append({
                    "id_radical": rad['id_radical'],
                    "nome": rad['nome'],
                    "classificacao": rad['classificacao'],
                    "ordem": tr['ordem']
                })
        
        # Embaralha as opções para o desafio do aluno no front
        random.shuffle(radicais_opcoes)

        return jsonify({
            "termo_id": termo_id,
            "definicao": termo['definicao_biologica'],
            "radicais": radicais_opcoes,
            "tipo": "montagem"
        }), 200
    except Exception as e:
        return jsonify({"erro": "Erro ao iniciar jogo de montagem", "detalhes": str(e)}), 500

@app.route('/api/jogos/montagem/answer', methods=['POST'])
@login_required
def verificar_montagem():
    """Valida o arranjo dos radicais enviado pelo usuário e pontua via RPC."""
    data = request.get_json() or {}
    termo_id = data.get('termo_id')
    ordem_usuario = data.get('ordem')  # Espera uma lista de IDs de radicais
    turma_id = data.get('turma_id')
    trilha_id = data.get('trilha_id')

    if not termo_id or not ordem_usuario:
        return jsonify({"erro": "Parâmetros incompletos"}), 400

    try:
        associacoes = supabase.table("termo_radicais").select("ordem, fk_radical").eq("fk_termo", termo_id).order("ordem").execute()
        ordem_correta = [a['fk_radical'] for a in associacoes.data]

        if ordem_usuario == ordem_correta:
            # Invoca a procedure RPC configurada no banco de dados Postgres
            if turma_id:
                supabase.rpc("incrementar_pontuacao", {"p_usuario": request.user.id, "p_turma": int(turma_id)}).execute()
            
            if trilha_id and turma_id:
                turma_trilha = supabase.table("turma_trilha").select("id").eq("fk_turma", turma_id).eq("fk_trilha", trilha_id).execute()
                if turma_trilha.data:
                    supabase.table("usuario_trilha_termo").upsert({
                        "fk_usuario": request.user.id,
                        "fk_turma_trilha": turma_trilha.data[0]['id'],
                        "fk_termo": termo_id,
                        "acertou": True
                    }, on_conflict="fk_usuario, fk_turma_trilha, fk_termo").execute()

            # Dispara a mecânica automática do deck de estudos (Anki active recall)
            flashcard = criar_flashcard_automatico(request.user.id, termo_id)
            return jsonify({"correto": True, "flashcard": flashcard}), 200
        
        return jsonify({"correto": False}), 200
    except Exception as e:
        return jsonify({"erro": "Erro ao processar resposta", "detalhes": str(e)}), 500

# -------------------------------------------------------------------
# Gerenciamento de Flashcards (Algoritmo Sistema de Repetição Espaçada)
# -------------------------------------------------------------------
def criar_flashcard_automatico(user_id, termo_id):
    """Cria um flashcard no deck de estudos ou ativa caso esteja oculto."""
    existente = supabase.table("flashcards").select("*").eq("fk_usuario", user_id).eq("fk_termo", termo_id).execute()
    if existente.data:
        if existente.data[0]['ativo']:
            return {"id": existente.data[0]['id_flashcard'], "show_modal": False}
        else:
            supabase.table("flashcards").update({"ativo": True}).eq("id_flashcard", existente.data[0]['id_flashcard']).execute()
            return {"id": existente.data[0]['id_flashcard'], "show_modal": True}
    else:
        novo = supabase.table("flashcards").insert({
            "fk_usuario": user_id,
            "fk_termo": termo_id,
            "ativo": True,
            "dificuldade": "fácil",
            "proxima_revisao_em": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            "criado_em": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        }).execute()
        return {"id": novo.data[0]['id_flashcard'], "show_modal": True}

@app.route('/api/flashcards', methods=['GET'])
@login_required
def listar_flashcards():
    """Filtra e exibe os cartões ativos e agendados para revisão no momento atual."""
    user_id = request.user.id
    dificuldade = request.args.get('dificuldade')
    now_str = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    try:
        # Traz apenas cartões cuja data de revisão já venceu ou é igual a agora (.lte)
        query = supabase.table("flashcards").select("*, termos(palavra_completa, definicao_biologica)") \
            .eq("fk_usuario", user_id) \
            .eq("ativo", True) \
            .lte("proxima_revisao_em", now_str)
            
        if dificuldade:
            query = query.eq("dificuldade", dificuldade)
            
        result = query.execute()
        return jsonify(result.data), 200
    except Exception as e:
        return jsonify({"erro": "Erro ao carregar flashcards", "detalhes": str(e)}), 500

@app.route('/api/flashcards/<int:flashcard_id>/review', methods=['PUT'])
@login_required
def revisar_flashcard(flashcard_id):
    """Aplica o algoritmo espaçado alterando a data futura conforme o acerto/erro."""
    data = request.get_json() or {}
    acertou = data.get('acertou')
    
    if acertou is None:
        return jsonify({"erro": "O campo informando o acerto/erro ('acertou') é mandatório"}), 400

    try:
        if acertou:
            nova_dificuldade = "fácil"
            # Se fixou bem o conteúdo, joga a revisão 3 dias para frente
            futuro = datetime.utcnow() + timedelta(days=3)
        else:
            nova_dificuldade = "difícil"
            # Se errou ou teve dificuldades, força a revisão rápida em 1 hora
            futuro = datetime.utcnow() + timedelta(hours=1)

        proxima_revisao = futuro.strftime('%Y-%m-%dT%H:%M:%SZ')

        supabase.table("flashcards").update({
            "dificuldade": nova_dificuldade,
            "proxima_revisao_em": proxima_revisao
        }).eq("id_flashcard", flashcard_id).eq("fk_usuario", request.user.id).execute()

        return jsonify({"mensagem": "Revisão agendada com sucesso!", "proxima_revisao": proxima_revisao}), 200
    except Exception as e:
        return jsonify({"erro": "Falha ao registrar revisão", "detalhes": str(e)}), 500

# -------------------------------------------------------------------
# Status da API (Healthcheck)
# -------------------------------------------------------------------
@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        "status": "online",
        "motor": "PostgreSQL (Supabase)",
        "timestamp": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    }), 200

@app.route('/')
def home():
    return jsonify({
        "projeto": "BioNexus API — Sistema de Navegação Morfológica",
        "endpoints_principais": ["/api/auth/login", "/api/terms", "/api/flashcards", "/api/status"]
    }), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)