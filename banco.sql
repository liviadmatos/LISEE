-- =======================================================
-- SCRIPT DE CRIAÇÃO DO BANCO DE DADOS (SUPABASE)
-- BASEADO NO app.py E NO PROMPT DE ESPECIFICAÇÃO
-- =======================================================

-- 0. Remover tabelas existentes para recriar do zero
DROP TABLE IF EXISTS flashcards CASCADE;
DROP TABLE IF EXISTS usuario_trilha_termo CASCADE;
DROP TABLE IF EXISTS turma_trilha CASCADE;
DROP TABLE IF EXISTS trilha_termos CASCADE;
DROP TABLE IF EXISTS trilhas CASCADE;
DROP TABLE IF EXISTS usuario_turma CASCADE;
DROP TABLE IF EXISTS turmas CASCADE;
DROP TABLE IF EXISTS termo_radicais CASCADE;
DROP TABLE IF EXISTS termos CASCADE;
DROP TABLE IF EXISTS radicais CASCADE;
DROP TABLE IF EXISTS usuarios CASCADE;

-- =======================================================
-- 1. TABELA DE USUÁRIOS
-- =======================================================
CREATE TABLE usuarios (
    id_usuario UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    perfil TEXT CHECK (perfil IN ('Aluno', 'Professor')) NOT NULL,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- =======================================================
-- 2. TABELA DE RADICAIS
-- =======================================================
CREATE TABLE radicais (
    id_radical SERIAL PRIMARY KEY,
    nome TEXT UNIQUE NOT NULL,
    significado TEXT,
    classificacao TEXT CHECK (classificacao IN ('Prefixo', 'Radical', 'Sufixo')) NOT NULL
);

-- =======================================================
-- 3. TABELA DE TERMOS BIOLÓGICOS
-- =======================================================
CREATE TABLE termos (
    id_termo SERIAL PRIMARY KEY,
    palavra_completa TEXT NOT NULL,
    definicao_biologica TEXT,
    area TEXT DEFAULT 'Geral'  -- Filtro obrigatório conforme especificação
);

-- =======================================================
-- 4. ASSOCIAÇÃO TERMO-RADICAIS (ordem para o jogo de montagem)
-- =======================================================
CREATE TABLE termo_radicais (
    id_associacao SERIAL PRIMARY KEY,
    fk_termo INTEGER REFERENCES termos(id_termo) ON DELETE CASCADE,
    fk_radical INTEGER REFERENCES radicais(id_radical) ON DELETE CASCADE,
    ordem INTEGER NOT NULL,  -- Ordem correta para o jogo de montagem
    UNIQUE(fk_termo, ordem)
);

-- =======================================================
-- 5. TABELA DE TURMAS
-- =======================================================
CREATE TABLE turmas (
    id_turma SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    codigo TEXT UNIQUE NOT NULL,  -- Código gerado automaticamente (6 caracteres)
    fk_professor UUID REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- =======================================================
-- 6. MATRÍCULA DE ALUNOS EM TURMAS
-- =======================================================
CREATE TABLE usuario_turma (
    id SERIAL PRIMARY KEY,
    fk_usuario UUID REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    fk_turma INTEGER REFERENCES turmas(id_turma) ON DELETE CASCADE,
    pontuacao INTEGER DEFAULT 0,  -- Ranking dos alunos
    data_ingresso TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(fk_usuario, fk_turma)
);

-- =======================================================
-- 7. TRILHAS DE APRENDIZADO (criadas pelo professor)
-- =======================================================
CREATE TABLE trilhas (
    id_trilha SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    fk_professor UUID REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- =======================================================
-- 8. TERMOS QUE COMPÕEM UMA TRILHA
-- =======================================================
CREATE TABLE trilha_termos (
    id SERIAL PRIMARY KEY,
    fk_trilha INTEGER REFERENCES trilhas(id_trilha) ON DELETE CASCADE,
    fk_termo INTEGER REFERENCES termos(id_termo) ON DELETE CASCADE,
    UNIQUE(fk_trilha, fk_termo)
);

-- =======================================================
-- 9. ATRIBUIÇÃO DE TRILHA A UMA TURMA (instância separada por turma)
-- =======================================================
CREATE TABLE turma_trilha (
    id SERIAL PRIMARY KEY,
    fk_turma INTEGER REFERENCES turmas(id_turma) ON DELETE CASCADE,
    fk_trilha INTEGER REFERENCES trilhas(id_trilha) ON DELETE CASCADE,
    nome_instancia TEXT NOT NULL,  -- Ex: "Citologia 2A", "Citologia 2B"
    data_atribuicao TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(fk_turma, fk_trilha)
);

-- =======================================================
-- 10. PROGRESSO DO ALUNO POR TERMO NA TRILHA
-- =======================================================
CREATE TABLE usuario_trilha_termo (
    id SERIAL PRIMARY KEY,
    fk_usuario UUID REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    fk_turma_trilha INTEGER REFERENCES turma_trilha(id) ON DELETE CASCADE,
    fk_termo INTEGER REFERENCES termos(id_termo) ON DELETE CASCADE,
    acertou BOOLEAN DEFAULT FALSE,
    data_resposta TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(fk_usuario, fk_turma_trilha, fk_termo)
);

-- =======================================================
-- 11. FLASHCARDS (criados automaticamente pelo sistema)
-- =======================================================
CREATE TABLE flashcards (
    id_flashcard SERIAL PRIMARY KEY,
    fk_usuario UUID REFERENCES usuarios(id_usuario) ON DELETE CASCADE,
    fk_termo INTEGER REFERENCES termos(id_termo) ON DELETE CASCADE,
    ativo BOOLEAN DEFAULT TRUE,
    dificuldade TEXT CHECK (dificuldade IN ('fácil', 'médio', 'difícil')) DEFAULT 'fácil',
    proxima_revisao_em TIMESTAMPTZ DEFAULT NOW(),  -- Algoritmo de repetição espaçada
    criado_em TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(fk_usuario, fk_termo)
);

-- =======================================================
-- 12. ÍNDICES PARA PERFORMANCE
-- =======================================================
-- Para buscas de termos por área
CREATE INDEX IF NOT EXISTS idx_termos_area ON termos(area);

-- Para buscas de radicais por nome
CREATE INDEX IF NOT EXISTS idx_radicais_nome ON radicais(nome);

-- Para associações termo-radical
CREATE INDEX IF NOT EXISTS idx_termo_radicais_termo ON termo_radicais(fk_termo);
CREATE INDEX IF NOT EXISTS idx_termo_radicais_radical ON termo_radicais(fk_radical);

-- Para turmas por professor
CREATE INDEX IF NOT EXISTS idx_turmas_professor ON turmas(fk_professor);

-- Para matrículas
CREATE INDEX IF NOT EXISTS idx_usuario_turma_usuario ON usuario_turma(fk_usuario);
CREATE INDEX IF NOT EXISTS idx_usuario_turma_turma ON usuario_turma(fk_turma);

-- Para trilhas
CREATE INDEX IF NOT EXISTS idx_trilhas_professor ON trilhas(fk_professor);

-- Para progresso do aluno
CREATE INDEX IF NOT EXISTS idx_usuario_trilha_termo_busca ON usuario_trilha_termo(fk_usuario, fk_turma_trilha);

-- Para flashcards (busca por revisão)
CREATE INDEX IF NOT EXISTS idx_flashcards_usuario ON flashcards(fk_usuario, proxima_revisao_em) WHERE ativo = TRUE;

-- =======================================================
-- 13. FUNÇÕES RPC (Remote Procedure Calls)
-- =======================================================

-- Função para incrementar pontuação do aluno (ranking)
CREATE OR REPLACE FUNCTION incrementar_pontuacao(p_usuario UUID, p_turma INTEGER)
RETURNS VOID AS $$
BEGIN
    -- Verifica se o usuário está matriculado na turma
    IF NOT EXISTS (
        SELECT 1 FROM usuario_turma 
        WHERE fk_usuario = p_usuario AND fk_turma = p_turma
    ) THEN
        RAISE EXCEPTION 'Usuário não está matriculado nesta turma';
    END IF;
    
    UPDATE usuario_turma
    SET pontuacao = pontuacao + 1
    WHERE fk_usuario = p_usuario AND fk_turma = p_turma;
END;
$$ LANGUAGE plpgsql;

-- Função para obter o ranking da turma
CREATE OR REPLACE FUNCTION obter_ranking_turma(p_turma INTEGER)
RETURNS TABLE(
    posicao BIGINT,
    nome_usuario TEXT,
    pontuacao INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ROW_NUMBER() OVER (ORDER BY ut.pontuacao DESC) as posicao,
        u.nome as nome_usuario,
        ut.pontuacao
    FROM usuario_turma ut
    JOIN usuarios u ON u.id_usuario = ut.fk_usuario
    WHERE ut.fk_turma = p_turma
    ORDER BY ut.pontuacao DESC;
END;
$$ LANGUAGE plpgsql;

-- Função para obter progresso do aluno em uma trilha
CREATE OR REPLACE FUNCTION obter_progresso_trilha(
    p_usuario UUID,
    p_turma_trilha INTEGER
)
RETURNS TABLE(
    total_termos BIGINT,
    termos_acertados BIGINT,
    progresso NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(DISTINCT tt.fk_termo) as total_termos,
        COUNT(DISTINCT CASE WHEN utt.acertou = TRUE THEN utt.fk_termo END) as termos_acertados,
        ROUND(
            (COUNT(DISTINCT CASE WHEN utt.acertou = TRUE THEN utt.fk_termo END)::NUMERIC / 
             COUNT(DISTINCT tt.fk_termo)::NUMERIC) * 100, 
            2
        ) as progresso
    FROM trilha_termos tt
    LEFT JOIN usuario_trilha_termo utt ON 
        utt.fk_termo = tt.fk_termo AND 
        utt.fk_usuario = p_usuario AND
        utt.fk_turma_trilha = p_turma_trilha
    WHERE tt.fk_trilha = (
        SELECT fk_trilha FROM turma_trilha WHERE id = p_turma_trilha
    );
END;
$$ LANGUAGE plpgsql;

-- =======================================================
-- 14. CONFIGURAÇÃO DE SEGURANÇA (ROW LEVEL SECURITY)
-- =======================================================

-- Habilitar RLS em todas as tabelas
ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE radicais ENABLE ROW LEVEL SECURITY;
ALTER TABLE termos ENABLE ROW LEVEL SECURITY;
ALTER TABLE termo_radicais ENABLE ROW LEVEL SECURITY;
ALTER TABLE turmas ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuario_turma ENABLE ROW LEVEL SECURITY;
ALTER TABLE trilhas ENABLE ROW LEVEL SECURITY;
ALTER TABLE trilha_termos ENABLE ROW LEVEL SECURITY;
ALTER TABLE turma_trilha ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuario_trilha_termo ENABLE ROW LEVEL SECURITY;
ALTER TABLE flashcards ENABLE ROW LEVEL SECURITY;

-- =======================================================
-- POLÍTICAS PARA USUÁRIOS
-- =======================================================

-- Usuários: leitura pública, atualização apenas pelo próprio
CREATE POLICY "Usuarios_leitura_publica" ON usuarios FOR SELECT USING (true);
CREATE POLICY "Usuarios_atualizacao_propria" ON usuarios FOR UPDATE USING (auth.uid() = id_usuario);
CREATE POLICY "Usuarios_insercao_propria" ON usuarios FOR INSERT WITH CHECK (auth.uid() = id_usuario);

-- =======================================================
-- POLÍTICAS PARA DICIONÁRIO (leitura pública)
-- =======================================================

CREATE POLICY "Radicais_leitura_publica" ON radicais FOR SELECT USING (true);
CREATE POLICY "Termos_leitura_publica" ON termos FOR SELECT USING (true);
CREATE POLICY "Termo_radicais_leitura_publica" ON termo_radicais FOR SELECT USING (true);

-- =======================================================
-- POLÍTICAS PARA TURMAS
-- =======================================================

-- Professor pode fazer tudo com suas turmas
CREATE POLICY "Turmas_professor_gestao" ON turmas 
    FOR ALL USING (auth.uid() = fk_professor);

-- Aluno pode ver turmas que participa
CREATE POLICY "Turmas_aluno_leitura" ON turmas 
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM usuario_turma 
            WHERE usuario_turma.fk_turma = turmas.id_turma 
            AND usuario_turma.fk_usuario = auth.uid()
        )
    );

-- =======================================================
-- POLÍTICAS PARA MATRÍCULAS
-- =======================================================

-- Aluno gerencia suas matrículas
CREATE POLICY "Usuario_turma_aluno_gestao" ON usuario_turma 
    FOR ALL USING (fk_usuario = auth.uid());

-- Professor pode ver matrículas de suas turmas
CREATE POLICY "Usuario_turma_professor_leitura" ON usuario_turma 
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM turmas 
            WHERE turmas.id_turma = usuario_turma.fk_turma 
            AND turmas.fk_professor = auth.uid()
        )
    );

-- =======================================================
-- POLÍTICAS PARA TRILHAS
-- =======================================================

-- Professor gerencia suas trilhas
CREATE POLICY "Trilhas_professor_gestao" ON trilhas 
    FOR ALL USING (auth.uid() = fk_professor);

-- Aluno vê trilhas de suas turmas
CREATE POLICY "Trilhas_aluno_leitura" ON trilhas 
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM turma_trilha tt
            JOIN usuario_turma ut ON ut.fk_turma = tt.fk_turma
            WHERE tt.fk_trilha = trilhas.id_trilha
            AND ut.fk_usuario = auth.uid()
        )
    );

-- =======================================================
-- POLÍTICAS PARA TRILHA_TERMOS
-- =======================================================

CREATE POLICY "Trilha_termos_leitura" ON trilha_termos 
    FOR SELECT USING (true);

-- Professor pode gerenciar termos das suas trilhas
CREATE POLICY "Trilha_termos_professor_gestao" ON trilha_termos 
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM trilhas 
            WHERE trilhas.id_trilha = trilha_termos.fk_trilha 
            AND trilhas.fk_professor = auth.uid()
        )
    );

-- =======================================================
-- POLÍTICAS PARA TURMA_TRILHA
-- =======================================================

CREATE POLICY "Turma_trilha_leitura" ON turma_trilha 
    FOR SELECT USING (true);

-- Professor gerencia atribuições das suas turmas
CREATE POLICY "Turma_trilha_professor_gestao" ON turma_trilha 
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM turmas 
            WHERE turmas.id_turma = turma_trilha.fk_turma 
            AND turmas.fk_professor = auth.uid()
        )
    );

-- =======================================================
-- POLÍTICAS PARA USUARIO_TRILHA_TERMO (progresso)
-- =======================================================

-- Aluno gerencia seu próprio progresso
CREATE POLICY "Usuario_trilha_termo_aluno_gestao" ON usuario_trilha_termo 
    FOR ALL USING (fk_usuario = auth.uid());

-- Professor vê progresso dos alunos das suas turmas
CREATE POLICY "Usuario_trilha_termo_professor_leitura" ON usuario_trilha_termo 
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM turma_trilha tt
            JOIN turmas t ON t.id_turma = tt.fk_turma
            WHERE tt.id = usuario_trilha_termo.fk_turma_trilha
            AND t.fk_professor = auth.uid()
        )
    );

-- =======================================================
-- POLÍTICAS PARA FLASHCARDS
-- =======================================================

-- Apenas o próprio usuário gerencia seus flashcards
CREATE POLICY "Flashcards_usuario_gestao" ON flashcards 
    FOR ALL USING (auth.uid() = fk_usuario);

-- =======================================================
-- 15. DADOS DE EXEMPLO (OPCIONAL - PARA TESTES)
-- =======================================================

-- Inserir alguns radicais de exemplo
INSERT INTO radicais (nome, significado, classificacao) VALUES
('bio', 'vida', 'Radical'),
('logos', 'estudo', 'Sufixo'),
('geo', 'terra', 'Prefixo'),
('fago', 'comer', 'Radical'),
('filo', 'amor', 'Radical');

-- Inserir alguns termos de exemplo
INSERT INTO termos (palavra_completa, definicao_biologica, area) VALUES
('Biologia', 'Ciência que estuda a vida', 'Geral'),
('Geofagia', 'Ingestão de terra', 'Ecologia'),
('Filosofia', 'Amor pelo conhecimento', 'Geral');

-- Associar radicais aos termos
INSERT INTO termo_radicais (fk_termo, fk_radical, ordem) VALUES
(1, 1, 1),  -- Bio + 
(1, 2, 2),  -- logos
(2, 3, 1),  -- geo +
(2, 4, 2),  -- fago
(3, 5, 1),  -- filo +
(3, 2, 2);  -- logos

-- Inserir um professor de exemplo (substitua o UUID pelo ID do usuário auth)
-- INSERT INTO usuarios (id_usuario, nome, email, perfil) 
-- VALUES ('seu-uuid-aqui', 'Professor Teste', 'professor@teste.com', 'Professor');

-- Inserir uma turma de exemplo
-- INSERT INTO turmas (nome, codigo, fk_professor) 
-- VALUES ('Biologia 2024', 'BIO123', 'seu-uuid-aqui');