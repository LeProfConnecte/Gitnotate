# -*- coding: utf-8 -*-
"""Données du moteur de redécouverte (redecouverte.py) : aucune fonction, aucune entrée-sortie.

Spécification du lot 4, annexes A à C :
  - CONCEPTS : lexique FR <-> EN de la recherche. id -> (classe, formes, voisins). Classe E (essentiel),
    F (faible, poids 0,3) ou C (contrainte : système, plateforme, langage de programmation, déploiement ;
    poids 0,5, jamais suffisante seule pour une correspondance forte quand le besoin nomme aussi son
    objet : « un OCR pour Windows » est d'abord un OCR). Les formes sont écrites naturellement (accents,
    mots ou expressions) et découpées par le tokenizer de l'index lui-même ; aucune forme par préfixe (pas
    de faux amis). Les voisins donnent une correspondance partielle (facteur 0,5), rendue symétrique par
    le moteur.
  - Mots vides (formes repliées, sans accents) : MOTS_VIDES (texte courant, aussi utilisés pour la
    négation dans les fiches) et MOTS_VIDES_REQUETE (cadre de question, en français et en anglais).
  - Déclencheurs de la requête : NEGATIONS (et FIN_NEGATION, NEGATION_ANNULEE), POSSESSIFS (contexte,
    sauf suivis de PROPRE : « mon propre serveur » désigne l'objet à créer), REFERENCES et
    EXPRESSIONS_REFERENCE (« alternative à … », « plus simple que … ») ; ils sont testés avant les mots vides.
  - IDENTIFIANTS (produits et plateformes nommés : rôle cible, contexte, référence ou exclusion) et
    PREPOSITIONS_CONTEXTE.
  - Exclusions d'un identifiant : EXIGENCES, SOUPLES, SOUPLES_EXPRESSIONS, ARTEFACTS (preuves lues dans les
    fiches) et LIAISONS_EXCLUSION (« pas avec Docker »).
  - FORMES_FICHES : formes cherchées dans les fiches seulement.
  - COMPOSITIONS : un concept et un mot hors lexique de la même requête lus ensemble (« recherche sémantique »
    + « code » : recherche de code, pas de documents).
  - INVARIABLES (jamais mis au singulier) et FAUX_AMIS (formes interdites dans un concept, vérifiées
    par les tests).
  - Gabarits de cas d'usage des versions 7.2 et antérieures (annexe C) : textes de remplissage que ces
    versions écrivaient sans lire le dépôt (liste générique anglaise, ou sa traduction par le LLM). Les
    lignes sont comparées après repli (gitnotate._fold), puces et ponctuation finale retirées ; les
    expressions françaises sont compilées une fois par le moteur.

Modifier les concepts, les mots vides ou les déclencheurs n'exige pas de resynchronisation : l'index garde
le texte des fiches. Exception : les gabarits GABARITS_CAS_USAGE_EN et GABARITS_CAS_USAGE_FR sont appliqués
à l'indexation (fiabilité des Cas d'usage, version de la fiche) ; après les avoir modifiés, relancez
« python redecouverte.py sync » (ou « sync --depuis » une capture).
"""

E, F, C = 'essentiel', 'faible', 'contrainte'

CONCEPTS = {
    'pdf': (E, ['pdf', 'fichier pdf', 'pdfs'], ['document']),
    'document': (E, ['document', 'documents', 'documentaire', 'docx', 'pptx', 'odt', 'fichier word',
        'document word', 'microsoft word', 'traitement documentaire', 'traitement de documents',
        'document processing', 'gestion documentaire'], ['pdf']),
    'documentation': (F, ['documentation', 'docs'], []),
    'ocr': (E, ['ocr', 'reconnaissance optique de caractères', 'reconnaissance de caractères',
        'reconnaissance de texte', 'text recognition', 'optical character recognition'],
        ['scan', 'extraction']),
    'scan': (E, ['scanné', 'scannés', 'scannée', 'scannées', 'scanner', 'scan', 'scans', 'scanned',
        'numériser', 'numérisé', 'numérisés', 'numérisation', 'digitize', 'digitization'], ['ocr']),
    'extraction': (E, ['extraire', 'extraction', 'extracteur', 'extract', 'extracts', 'extracting',
        'extracted', 'extractor', 'parse', 'parser', 'parsing', 'parsed', 'convertir', 'convertit',
        'conversion', 'converti', 'convertisseur', 'convert', 'converts', 'converter', 'linéariser',
        'linearize'], ['ocr']),
    'tableau': (E, ['tableau', 'tableaux', 'table', 'tables', 'tabular', 'tabulaire'], ['tableur']),
    'tableur': (E, ['excel', 'xlsx', 'csv', 'feuille de calcul', 'feuilles de calcul', 'spreadsheet',
        'spreadsheets', 'tableur'], ['tableau']),
    'mise_en_page': (E, ['mise en page', 'layout'], []),
    'markdown': (E, ['markdown'], []),
    'formule': (E, ['formule', 'formules', 'formula', 'formulas', 'équation', 'équations', 'equation',
        'equations', 'latex'], []),
    'presentation': (E, ['diaporama', 'diaporamas', 'slides', 'slide deck', 'powerpoint'], ['document']),
    'btp': (E, ['btp', 'bâtiment', 'bâtiments', 'génie civil', 'civil engineering', 'chantier', 'chantiers',
        'travaux publics', 'économie de la construction', 'construction site'], ['bim', 'metre']),
    'bim': (E, ['bim', 'ifc', 'revit', 'maquette numérique', 'building information modeling'], ['btp', 'cao']),
    'cao': (E, ['cao', 'dao', 'cad', 'autocad', 'dwg', 'dxf', 'dessin technique',
        'dessin assisté par ordinateur'], ['plan']),
    'plan': (E, ['plan', 'plans', 'plan de masse', 'blueprint', 'blueprints'], ['cao', 'bim']),
    'metre': (E, ['métré', 'métrés', 'avant-métré', 'quantity takeoff', 'takeoff', 'dpgf', 'dqe',
        'bordereau de prix', 'devis quantitatif'], ['btp']),
    'cctp': (E, ['cctp', 'ccap', 'dce', 'cahier des charges', 'pièces écrites'], ['document']),
    'structure': (E, ['calcul de structure', 'calculs de structure', 'calcul de structures', 'calculs de structures',
        'calcul des structures', 'résistance des matériaux', 'rdm',
        'éléments finis', 'finite element', 'eurocode', 'eurocodes', 'béton armé'], ['btp']),
    'topographie': (E, ['topographie', 'géomètre', 'lidar', 'nuage de points', 'point cloud',
        'photogrammétrie', 'photogrammetry'], ['3d']),
    '3d': (E, ['3d', 'modèle 3d', '3d model', 'maillage', 'mesh'], []),
    'carto': (E, ['cartographie', 'cartographique', 'sig', 'gis', 'géospatial', 'géospatiale', 'geospatial',
        'openstreetmap'], []),
    'enseignement': (E, ['enseignement', 'enseigner', 'enseignant', 'enseignants', 'pédagogique',
        'pédagogiques', 'pédagogie', 'éducatif', 'éducative', 'éducation', 'education', 'educational',
        'teaching', 'teacher', 'teachers', 'scolaire', 'formation'], ['cours', 'eleve']),
    'cours': (E, ['cours', 'leçon', 'leçons', 'lesson', 'lessons', 'course', 'courses', 'tutoriel',
        'tutoriels', 'tutorial', 'tutorials', 'supports de cours', 'support de cours', 'curriculum',
        'débutants', 'for beginners', 'beginners'], ['enseignement']),
    'eleve': (E, ['élève', 'élèves', 'étudiant', 'étudiants', 'étudiante', 'student', 'students', 'apprenant',
        'apprenants', 'learner', 'learners'], ['enseignement']),
    'qcm': (E, ['qcm', 'quiz', 'quizz', 'questionnaire à choix multiples', 'multiple choice', 'mcq',
        'questionnaire', 'questionnaires', 'fiches de révision', 'fiche de révision', 'flashcard',
        'flashcards'], ['exercice']),
    'exercice': (E, ['exercice', 'exercices', 'exercise', 'exercises', 'travaux dirigés', 'devoir', 'devoirs',
        'homework', 'corrigé', 'corrigés'], ['qcm']),
    'lms': (E, ['moodle', 'lms', "plateforme d'apprentissage", 'learning management', 'e-learning'],
        ['enseignement']),
    # Gestion de la classe (absences, notes, bulletins) : sans voisin, ce n'est pas un outil pédagogique
    'vie_scolaire': (E, ['vie scolaire', 'absences', 'absentéisme', 'assiduité', 'feuille de présence',
        'feuilles de présence', "feuille d'appel", 'attendance', 'carnet de notes', 'bulletin de notes',
        'bulletins de notes', 'relevé de notes', 'relevés de notes', 'gradebook', 'pronote'], []),
    'tts': (E, ['synthèse vocale', 'tts', 'text to speech', 'speech synthesis', 'voix off', 'voice over',
        'voiceover', 'lecture vocale', 'voice cloning', 'clonage de voix'], ['voix']),
    'voix': (E, ['voix', 'voice', 'voices', 'vocal', 'vocale', 'vocales', 'speech', 'parole'], ['tts', 'stt']),
    'stt': (E, ['reconnaissance vocale', 'speech to text', 'stt', 'transcription', 'transcrire', 'transcribe',
        'speech recognition', 'asr'], ['soustitre', 'voix']),
    'soustitre': (E, ['sous-titres', 'sous-titre', 'sous-titrage', 'subtitle', 'subtitles', 'caption',
        'captions', 'srt'], ['stt']),
    'video': (E, ['vidéo', 'vidéos', 'video', 'videos', 'clip', 'clips'], []),
    'video_courte': (E, ['vidéo courte', 'vidéos courtes', 'short video', 'short videos', 'shorts', 'reels',
        'tiktok', 'youtube shorts', 'format court'], ['video']),
    'montage': (E, ['montage vidéo', 'video editing', 'éditeur vidéo', 'édition vidéo', 'video editor'],
        ['video']),
    'image_gen': (E, ["génération d'images", 'générer des images', 'image generation', 'text to image',
        'stable diffusion', 'diffusion model'], ['image']),
    'image': (E, ['image', 'images', 'photo', 'photos', 'picture', 'pictures', 'illustration', 'illustrations'],
        []),
    'audio': (E, ['audio', 'sound', 'musique', 'music'], ['voix']),
    'avatar': (E, ['avatar', 'avatars', 'talking head', 'tête parlante', 'lipsync', 'lip sync'], ['video']),
    'podcast': (E, ['podcast', 'podcasts'], ['audio']),
    'donnees': (F, ['données', 'data', 'donnée'], []),
    'jeu_donnees': (E, ['jeu de données', 'jeux de données', 'dataset', 'datasets', 'open data',
        'données ouvertes', 'données publiques'], ['donnees']),
    'tableau_bord': (E, ['tableau de bord', 'tableaux de bord', 'dashboard', 'dashboards', 'dataviz',
        'data visualization', 'visualisation de données', 'visualiser des données'], ['visualisation']),
    'visualisation': (E, ['visualisation', 'visualization', 'graphique', 'graphiques', 'chart', 'charts',
        'plot', 'plots', 'courbe', 'courbes'], ['tableau_bord']),
    'notebook': (E, ['notebook', 'notebooks', 'jupyter', 'carnet'], []),
    'bdd': (E, ['base de données', 'bases de données', 'database', 'databases', 'sql', 'postgres',
        'postgresql', 'sqlite', 'mysql', 'supabase', 'mongodb'], []),
    'analyse_donnees': (E, ['analyse de données', 'analyse des données', 'data analysis', 'data science',
        'pandas', 'statistique', 'statistiques', 'statistics'], ['donnees']),
    'etl': (E, ['etl', 'ingestion', 'nettoyage de données', 'data cleaning', 'data pipeline'], ['donnees']),
    'finance': (E, ['finance', 'finances', 'financier', 'financière', 'financiers', 'financières', 'financial',
        'fintech', 'bourse', 'boursier', 'boursière', 'stock market', 'stocks', 'stock', 'investissement',
        'investir', 'invest', 'investing', 'investment', 'portefeuille', 'portfolio', 'hedge fund',
        'marchés financiers'], ['trading', 'donnees_marche']),
    'trading': (E, ['trading', 'trader', 'traders', 'algorithmic trading', 'trading algorithmique', 'backtest',
        'backtesting', 'backtests', 'indicateurs techniques', 'technical indicators'], ['finance']),
    'donnees_marche': (E, ['données de marché', 'market data', 'cotation', 'cotations', 'cours de bourse',
        'ticker', 'tickers', 'ohlc'], ['finance']),
    'budget': (E, ['budget', 'budgets', 'finances personnelles', 'personal finance', 'dépenses', 'expenses',
        'comptabilité', 'accounting'], ['finance']),
    'crypto': (E, ['crypto', 'cryptos', 'cryptomonnaie', 'cryptomonnaies', 'cryptocurrency',
        'cryptocurrencies', 'bitcoin', 'ethereum', 'web3', 'blockchain', 'on-chain', 'defi'], []),
    'veille': (E, ['veille', 'veilles', 'rss', 'flux rss', 'news', 'actualité', 'actualités', 'agrégateur',
        'aggregator', 'alerte', 'alertes', 'alert', 'alerts', 'newsletter', 'newsletters', 'rss feed', 'news feed',
        'news feeds'],
        ['monitoring', 'recherche_web']),
    'monitoring': (E, ['surveiller', 'surveille', 'surveillent', 'surveillance', 'monitor', 'monitors',
        'monitoring', 'supervision', 'superviser', 'observabilité', 'observability'], ['veille']),
    'recherche_web': (E, ['recherche approfondie', 'recherches approfondies', 'deep research', 'recherche web',
        'web research', 'research agent', 'agent de recherche'], ['veille', 'recherche']),
    'recherche': (F, ['recherche', 'recherches', 'rechercher', 'search', 'research'], []),
    'recherche_semantique': (E, ['recherche sémantique', 'semantic search', 'recherche hybride',
        'hybrid search'], ['rag', 'base_vectorielle']),
    # Recherche sémantique dans du code source (lot 5) : notion distincte, voisine de la recherche sémantique
    # générale (documents, PDF). Dans la requête, seules les formes où « code » s'intercale (« recherche de code
    # sémantique », « semantic code search ») ; « recherche sémantique dans le code » passe par COMPOSITIONS, qui
    # écarte les autres sens (« le Code de l'urbanisme »). Dans les fiches, aussi FORMES_FICHES.
    'recherche_code': (E, ['recherche de code sémantique', 'semantic code search', 'code semantic search'],
        ['recherche_semantique']),
    'automatisation': (E, ['automatiser', 'automatisation', 'automatisations', 'automatique',
        'automatiquement', 'automatisé', 'automatisée', 'automatisés', 'automatise', 'automatisent',
        'automate', 'automates', 'automation', 'automated', 'automating', 'tâches planifiées', 'cron'],
        ['workflow']),
    'workflow': (E, ['workflow', 'workflows', 'flux de travail', 'flux de travaux', 'orchestration'],
        ['automatisation', 'nocode']),
    # Identifiants de produits (lot 5, voir IDENTIFIANTS) : notions distinctes, sans voisin. Citer n8n ne dit pas
    # qu'une fiche parle de workflows (« Brique pour : Automatisations n8n »), ni qu'un besoin de workflows
    # demande n8n.
    'n8n': (E, ['n8n'], []),
    'zapier': (E, ['zapier'], []),
    'nocode': (E, ['no-code', 'sans code', 'low-code', 'nocode', 'lowcode', 'glisser-déposer', 'drag and drop'],
        ['workflow']),
    'scraping': (E, ['scraping', 'scraper', 'scrapers', 'scrape', 'scrapes', 'scraped', 'crawler', 'crawlers',
        'crawl', 'crawling', "robot d'exploration", 'extracteur web', 'web scraper', 'moissonnage'],
        ['site_web', 'extraction']),
    'site_web': (E, ['site web', 'sites web', 'site internet', 'sites internet', 'website', 'websites',
        'page web', 'pages web', 'web page', 'web pages', 'webpage', 'web', 'en ligne', 'online'],
        ['scraping']),
    'navigateur': (E, ['navigateur', 'navigateurs', 'browser', 'browsers', 'playwright', 'selenium',
        'puppeteer', 'naviguer', 'navigue', 'naviguent', 'browse', 'browsing'], ['scraping', 'agent']),
    'email': (E, ['e-mail', 'e-mails', 'email', 'emails', 'courriel', 'courriels', 'gmail', 'smtp'], []),
    'api': (E, ['api', 'apis', 'api rest', 'rest api', 'endpoint', 'endpoints', 'sdk'], []),
    'fastapi': (E, ['fastapi'], ['api', 'python']),
    'appli_web': (E, ['application web', 'applications web', 'web app', 'web apps', 'webapp'],
        ['frontend', 'site_web']),
    'frontend': (E, ['frontend', 'front-end', 'front end', 'interface utilisateur', 'user interface', 'ui',
        'gui', 'interface graphique', 'nextjs', 'vuejs', 'svelte'], ['appli_web']),
    'react': (E, ['react', 'reactjs'], ['frontend']),
    'backend': (E, ['backend', 'back-end', 'back end'], ['api']),
    'python': (C, ['python'], []),
    'javascript': (C, ['javascript', 'nodejs', 'typescript'], []),
    'docker': (C, ['docker', 'conteneur', 'conteneurs', 'container', 'containers', 'docker compose',
        'dockerfile'], ['auto_heberge']),
    'kubernetes': (C, ['kubernetes', 'k8s'], ['docker']),
    'auto_heberge': (E, ['auto-hébergé', 'auto-hébergée', 'auto-hébergés', 'auto-hébergées',
        'auto-hébergeable', 'auto-hébergeables', 'auto-hébergement', 'self-hosted', 'self-host',
        'self-hostable', 'selfhosted', 'self hosting', 'on-premise', 'vps'], ['docker', 'local']),
    'local': (C, ['local', 'locale', 'locaux', 'localement', 'en local', 'hors ligne', 'hors-ligne', 'offline',
        'on-device'], ['auto_heberge']),
    'windows': (C, ['windows'], []),
    'linux': (C, ['linux', 'ubuntu', 'debian'], []),
    'macos': (C, ['macos', 'mac os', 'osx', 'mac'], []),
    'gpu': (C, ['gpu', 'gpus', 'cuda', 'vram', 'nvidia', 'carte graphique', 'cartes graphiques'], []),
    'cli': (C, ['cli', 'ligne de commande', 'lignes de commande', 'command line', 'command-line', 'terminal'],
        []),
    'mobile': (E, ['mobile', 'smartphone', 'application mobile', 'applications mobiles', 'mobile app'],
        ['systeme_mobile']),
    'systeme_mobile': (C, ['android', 'ios'], ['mobile']),
    'auth': (E, ['authentification', 'authentication', 'oauth', 'sso', 'login'], []),
    'notion': (E, ['notion'], []),
    'mcp': (E, ['mcp', 'model context protocol'], []),
    'serveur': (E, ['serveur', 'serveurs', 'server', 'servers'], []),
    'connecteur': (E, ['connecter', 'connecte', 'connectent', 'connecteur', 'connecteurs', 'connector',
        'connectors', 'connect', 'relier', 'intégrer', 'intégrable', 'integrate', 'integration'], []),
    'llm': (F, ['llm', 'llms', 'modèle de langage', 'modèles de langage', 'grand modèle de langage',
        'language model', 'language models', 'large language model', 'gpt', 'chatgpt'], []),
    'ia': (F, ['ia', 'ai', 'intelligence artificielle', 'artificial intelligence', 'ia générative',
        'generative ai', 'genai'], []),
    'agent': (E, ['agent', 'agents', 'agentique', 'agentic', 'multi-agents', 'multi-agent', 'agent autonome',
        'agents autonomes', 'autonomous agent'], []),
    'agent_code': (E, ['agent de code', 'agents de code', 'agent de développement', 'agents de développement',
        'coding agent', 'coding agents', 'code agent', 'assistant de code', 'assistants de code',
        'assistant de programmation', 'coding assistant', 'ai coding', 'pair programming',
        'génération de code', 'code generation', 'assistance au code'], ['agent', 'claude_code']),
    'claude_code': (E, ['claude code'], ['agent_code']),
    'rag': (E, ['rag', 'génération augmentée', 'génération augmentée par récupération',
        'retrieval augmented generation', 'retrieval-augmented generation', 'base de connaissances',
        'bases de connaissances', 'knowledge base', 'chat with your documents', 'questions-réponses',
        'question answering'], ['base_vectorielle', 'recherche_semantique']),
    'base_vectorielle': (E, ['base vectorielle', 'bases vectorielles', 'base de données vectorielle',
        'vector database', 'vector databases', 'vector store', 'vector db', 'vectordb', 'embeddings',
        'embedding', 'recherche vectorielle', 'vector search', 'milvus', 'qdrant', 'chroma', 'pgvector',
        'faiss'], ['rag', 'recherche_semantique']),
    'memoire_agent': (E, ['mémoire à long terme', 'long-term memory', 'agent memory', 'mémoire des agents'],
        ['agent']),
    'chatbot': (E, ['chatbot', 'chatbots', 'agent conversationnel', 'assistant conversationnel',
        'interface de chat', 'chat interface'], []),
    'traduction': (E, ['traduction', 'traductions', 'traduire', 'traducteur', 'translate', 'translation',
        'translator'], ['multilingue']),
    'multilingue': (E, ['multilingue', 'multilingues', 'multilingual', 'plusieurs langues'],
        ['traduction', 'francais']),
    'francais': (E, ['français', 'française', 'french', 'francophone', 'langue française'], ['multilingue']),
    'resume': (E, ['résumé', 'résumés', 'résumer', 'synthèse', 'synthèses', 'summary', 'summaries',
        'summarize', 'summarization', 'compte rendu'], []),
    'prompt': (E, ['prompt', 'prompts', 'prompt engineering', 'ingénierie de prompt'], []),
    'finetune': (E, ['fine-tuning', 'finetuning', 'fine-tune', 'affinage', 'ajustement fin', 'réglage fin',
        'lora', 'qlora'], ['entrainement']),
    'entrainement': (E, ['entraîner', 'entraînement', 'training', 'train'], ['finetune']),
    'inference': (E, ['inférence', 'inference', 'quantization', 'quantification', 'gguf', 'ollama', 'vllm'],
        ['local', 'llm']),
    'vision': (E, ['vision par ordinateur', 'computer vision', 'vision-langage', 'vision-language', 'vlm',
        'multimodal', 'multimodale', 'multimodaux'], ['image']),
    'agent_gui': (E, ['agent gui', 'gui agent', 'computer use', "contrôle de l'ordinateur", 'screen parsing',
        "analyse d'écran", "capture d'écran", 'screenshot', 'screenshots'], ['agent', 'navigateur']),
    'liste': (E, ['awesome', 'liste organisée', 'curated list', 'liste collective', 'collection de',
        'liste de', 'listes de'], []),
    'opensource': (F, ['open source', 'open-source', 'opensource', 'logiciel libre', 'free software'], []),
    'gratuit': (F, ['gratuit', 'gratuite', 'gratuits', 'gratuites', 'free tier'], []),
    'licence': (E, ['licence', 'licences', 'license', 'licenses', 'licensing'], []),
    'commercial': (E, ['commercial', 'commerciale', 'commerciaux', 'commerciales', 'usage commercial',
        'commercial use'], []),
    'securite': (E, ['sécurité', 'security', 'pentest', 'vulnérabilité', 'vulnérabilités', 'vulnerability',
        'vulnerabilities', "test d'intrusion", 'cybersécurité', 'cybersecurity'], []),
    'generer': (F, ['générer', 'génère', 'génèrent', 'génération', 'générateur', 'generate', 'generates',
        'generation', 'generator', 'créer', 'crée', 'créez', 'create', 'creates', 'produire', 'produit',
        'produce'], []),
    'application': (F, ['application', 'applications', 'app', 'apps', 'software'], []),
    'technique': (F, ['technique', 'techniques', 'technical'], []),
    'jeu_video': (E, ['jeu vidéo', 'jeux vidéo', 'game', 'games', 'gaming', 'gamedev'], []),
    'prise_notes': (E, ['prise de notes', 'note-taking', 'notes structurées', 'obsidian'], []),
    'plateforme': (F, ['plateforme', 'plateformes', 'platform', 'platforms', 'framework', 'frameworks',
        'bibliothèque', 'bibliothèques', 'library', 'libraries', 'boîte à outils', 'toolkit'], []),
}

MOTS_VIDES = frozenset("""
a au aux avec ce ces cet cette d de des du elle elles en et eux il ils je j l la le les leur leurs lui
ma mais me meme mes moi mon n ne nos notre nous on ou par pour qu que qui s sa se ses son sur ta te tes
toi ton tu un une vos votre vous y c est sont ete etre avoir ont dans plus tres afin ainsi comme dont
sous ceci cela ca chaque tout tous toute toutes t m
the of and to in for on with by from at as is are was were be been it its this that these those an or
into via your you our we they their his her has have had do does can will would should could also than
then there here such per about i my me
""".split())

# Cadre de question : « Quels outils déjà enregistrés pourrais-je utiliser pour… », et son équivalent
# anglais « Which saved tools could I use to… » (aucun de ces mots n'est une forme du lexique)
MOTS_VIDES_REQUETE = frozenset("""
quel quels quelle quelles quoi deja enregistre enregistres enregistree enregistrees enregistrer
sauvegarde sauvegardes pourrais pourrait pourrions pourriez puis peux peut pouvoir as avez avons
existe existent ya utiliser utilise utilisable utilisables reutilisable reutilisables reutiliser
interessant interessante interessants interessantes projet projets depot depots repo repos chose
choses quelque truc trucs faire trouver cherche chercher besoin aider aide permettre permet
permettant seraient serait bien bon bons meilleur meilleurs recommander conseiller suggerer marque
necessite necessitent necessiter requiert requierent
marques quelqu celui celle ceux lesquels lequel laquelle exemple comment fonctionne fonctionner
fonctionnent tourner tourne servir sert place outil outils tool tools logiciel logiciels
exploitable exploitables
what which who whom whose where when how why may might please
use used uses using useful usable reuse reusable save saved stored bookmarked starred already
any some something anything existing project projects repository repositories need needs want
require requires requiring
looking find help good best recommend suggest
if whether si faut doit soit tant else
""".split())

NEGATIONS = frozenset({'sans', 'aucun', 'aucune', 'pas', 'ni', 'non', 'no', 'not', 'without', 'hors', 'jamais',
                       'never'})
FIN_NEGATION = frozenset({'pour', 'avec', 'et', 'ou', 'mais', 'afin', 'qui', 'dans', 'sur', 'for', 'with', 'and',
                          'or', 'but', 'in', 'on'})
NEGATION_ANNULEE = frozenset({'seulement', 'uniquement', 'only', 'just'})
POSSESSIFS = frozenset({'mes', 'mon', 'ma', 'my', 'nos', 'notre', 'our'})
# Après un possessif : « mon propre serveur », « my own server » (objet à créer, pas un contexte)
PROPRE = frozenset({'propre', 'propres', 'own'})
REFERENCES = frozenset({'alternative', 'alternatives', 'remplacant', 'remplacante', 'equivalent', 'equivalente',
                        'equivalents', 'similaire', 'similaires', 'replacement', 'replacements', 'substitute',
                        'remplacement'})
# Expressions de comparaison (écrites naturellement, découpées par le tokenizer de l'index) : ce qui suit est
# la référence à dépasser, pas l'objet cherché (« plus simple que la ligne de commande »)
EXPRESSIONS_REFERENCE = ('plus simple que', "plus simple qu'", 'plus facile que', "plus facile qu'", 'plutôt que',
                         "plutôt qu'", 'au lieu de', "au lieu d'", 'au lieu du', 'au lieu des', 'à la place de',
                         "à la place d'", 'à la place du', 'à la place des', 'mieux que', "mieux qu'",
                         'instead of', 'rather than', 'simpler than', 'easier than', 'better than')
# Compositions (lot 5) : (concept, mots libres, concept composé). Quand le concept et l'un des mots (forme repliée)
# sont dans le même segment de la requête, à PORTEE_COMPOSITION unités au plus, les deux deviennent le concept
# composé, avec le rôle du premier : « une recherche sémantique dans mon code source » cherche du code, pas des
# documents. Le mot ne compose pas s'il suit une négation (même fermée par une liaison : « not for source code »)
# ni dans un autre sens (CODE_AUTRES_SENS : « QR code », « Code de l'urbanisme », « building code »).
COMPOSITIONS = (
    ('recherche_semantique', frozenset({'code', 'codes', 'codebase', 'codebases'}), 'recherche_code'),
)
# Formes cherchées dans les fiches seulement (jamais reconnues dans la requête) : « recherche sémantique dans le
# code » d'une fiche parle de code ; dans une requête, la même suite peut être « … dans le Code de l'urbanisme »
FORMES_FICHES = {
    'recherche_code': ['recherche sémantique de code', 'recherche sémantique du code', 'recherche sémantique dans le code',
                       'semantic search over code', 'semantic search in code', 'semantic search for code',
                       'semantic search of code'],
}
# Mots repliés juste avant « code » (avant) ou dans les deux mots de contenu qui suivent (apres)
CODE_AUTRES_SENS = {
    'avant': frozenset({'qr', 'legal', 'legaux', 'juridique', 'juridiques', 'building', 'fire', 'postal', 'promo',
                        'zip', 'country', 'area', 'dress', 'tax', 'civil', 'penal', 'criminal', 'commercial',
                        'labor', 'labour', 'traffic', 'highway', 'tribal', 'municipal', 'comptable', 'comptables',
                        'fiscal', 'fiscaux', 'lignes', 'ligne', 'lines', 'line', 'little', 'peu', 'minimal',
                        'minimum', 'less', 'moins', 'zero', 'low', 'bar', 'access', 'error', 'status',
                        'discount', 'coupon', 'voucher', 'morse', 'color', 'colour', 'naf', 'ape', 'insee',
                        'rome', 'cpv', 'nace', 'sic', 'naics', 'hs', 'iso', 'swift', 'iban', 'bic', 'ean', 'vs',
                        'exemple', 'exemples', 'example', 'examples', 'sample', 'samples', 'snippet', 'snippets'}),
    'apres': frozenset({'travail', 'urbanisme', 'route', 'civil', 'commerce', 'penal', 'construction',
                        'environnement', 'sante', 'postal', 'couleur', 'couleurs', 'promo', 'promotionnel', 'legal',
                        'conduite', 'conduct', 'barre', 'barres', 'acces', 'secret', 'pin', 'qr', 'erreur',
                        'general', 'impots', 'monetaire', 'marches', 'commande', 'education', 'consommation',
                        'juridique', 'juridiques', 'comptable', 'comptables', 'fiscal', 'fiscaux', 'douanes',
                        'douanier', 'electoral', 'rural', 'forestier', 'minier', 'transports', 'defense',
                        'collectivites', 'procedure', 'propriete', 'famille', 'assurances', 'mutualite',
                        'communes', 'justice', 'deontologie', 'ape', 'naf', 'insee', 'tva', 'exemple', 'exemples',
                        'example', 'examples', 'sample', 'samples', 'snippet', 'snippets'}),
}
# Identifiants techniques nommés (lot 5) : concept -> (nature, catégorie). Leur rôle dépend de la requête :
#   - cible (« une bibliothèque de workflows pour n8n ») : le concept lui-même ;
#   - contrainte (après une préposition de PREPOSITIONS_CONTEXTE ou un possessif : « des workflows exécutés avec
#     n8n », « in my React app ») : un produit devient une contrainte (classe C, rôle normal), comptée dans la
#     couverture mais jamais suffisante pour « forte » ;
#   - référence (« une alternative no-code à n8n ») : un produit est remplacé par sa catégorie (son nom compris),
#     rôle référence, et devient une exclusion implicite : on cherche ce qui le remplace, pas ce qui en dépend ;
#   - exclusion (« sans n8n », « pas avec Docker ») : jamais une notion positive (voir le moteur).
# Nature « produit » : outil ou bibliothèque qu'on cherche ou qu'on remplace ; « plateforme » et « materiel » :
# déjà des contraintes (classe C), seule l'exclusion change.
IDENTIFIANTS = {
    'n8n': ('produit', 'workflow'), 'zapier': ('produit', 'workflow'), 'fastapi': ('produit', 'api'),
    'react': ('produit', 'frontend'), 'claude_code': ('produit', 'agent_code'),
    'docker': ('plateforme', None), 'kubernetes': ('plateforme', None), 'windows': ('plateforme', None),
    'linux': ('plateforme', None), 'macos': ('plateforme', None), 'gpu': ('materiel', None),
}
# Formes repliées ; « under » est exclu (hors mots vides, il deviendrait lui-même une notion)
PREPOSITIONS_CONTEXTE = frozenset({'avec', 'with', 'sous', 'sur', 'on', 'dans', 'in', 'into', 'via', 'using', 'en'})
# Exclusion d'un identifiant (lot 5, « sans n8n », « pas avec Docker », « without GPU ») : ce que dit chaque
# mention dans la fiche, jamais déduit de l'absence d'information (le moteur en tire sept états : requis, non
# requis, contradictoire, mention, inconnu, et l'avis du LLM seul, avis_requis ou avis_non_requis). Seul « requis »
# change le classement : il n'est retenu que sur une tournure sans ambiguïté ; dans le doute, « mention ». Mots
# repliés. Le « groupe » d'une mention s'arrête à une virgule, un point-virgule, une fin de phrase ou de ligne, mais
# pas à une parenthèse ni à un deux-points (« - GPU NVIDIA (optionnel) », « Docker: not required »).
#   - non requis : mention niée juste avant (« sans Docker », « ne nécessite pas de GPU », « Neither Docker nor a
#     GPU ») ou après (« Docker n'est pas requis », « GPU : non », « non pris en charge », « not supported »),
#     facultative tout près (SOUPLES, SOUPLES_EXPRESSIONS ; « GPU et Docker facultatifs » vaut pour les deux, « GPU
#     and optionally Docker » pour Docker seul), CPU possible pour le GPU, usage restreint (« uniquement utilisé pour
#     les tests », « n'est nécessaire que pour l'entraînement ») ou produit cité comme celui qu'on remplace
#     (« alternative à n8n », « substitute for Zapier ») ;
#   - mention : alternative (« Windows, macOS ou Linux », « Docker / Podman », plusieurs systèmes dans un même
#     élément ; pas « NVIDIA or AMD GPU » ni « CUDA 11.8 ou 12.1 »), ou aucun indice ;
#   - requis : verbe d'exigence au plus deux mots avant (EXIGENCES_VERBES : « Nécessite un GPU », « Requires
#     Python and Docker »), adjectif d'exigence juste après (EXIGENCES_ADJECTIFS : « Docker requis », « a GPU is
#     mandatory »), RESTRICTIFS collés (« Linux uniquement », « Docker only »), début d'un élément de la colonne
#     Prérequis (« - NVIDIA GPU with CUDA »), titre du dépôt qui commence par l'identifiant, ou, pour un produit,
#     « pour n8n » / « for React » et ARTEFACTS (« workflows n8n », « nœud n8n », « skills Claude Code »).
EXIGENCES_VERBES = frozenset({'necessite', 'necessitent', 'necessiter', 'requiert', 'requierent', 'exige', 'exigent',
                              'demande', 'demandent', 'depend', 'dependent', 'requires', 'require', 'requiring',
                              'needs', 'need', 'depends', 'faut', 'doit', 'doivent', 'must', 'suppose', 'supposent',
                              'assumes', 'presuppose'})
EXIGENCES_ADJECTIFS = frozenset({'requis', 'requise', 'requises', 'obligatoire', 'obligatoires', 'indispensable',
                                 'indispensables', 'necessaire', 'necessaires', 'exige', 'exigee', 'exiges', 'exigees',
                                 'required', 'mandatory', 'needed', 'necessary', 'minimum', 'minimal', 'minimale'})
EXIGENCES = EXIGENCES_VERBES | EXIGENCES_ADJECTIFS
# Après une négation : « non pris en charge », « not supported », « n'est pas un prérequis », « not a requirement »
# (participes et noms seulement : « does not support Windows » a un objet, il ne dit rien de l'identifiant)
PRISE_EN_CHARGE = frozenset({'pris', 'prise', 'supporte', 'supportee', 'supportes', 'supported', 'compatible',
                             'compatibles', 'prerequis', 'requirement', 'requirements', 'dependance', 'dependency',
                             'obligation'})
INCOMPATIBLES = frozenset({'incompatible', 'incompatibles', 'unsupported'})
# « Linux uniquement », « Docker only », « uniquement sous Windows » : exigence seulement collée à l'identifiant (un
# mot vide au plus entre les deux) ; suivis d'un usage (RESTRICTIFS_SOUPLES : « uniquement utilisé pour les tests »,
# « only needed for development ») ou d'un usage annexe (USAGES_ANNEXES après « pour » / « for » : « only for
# tests »), ils disent au contraire que l'identifiant n'est pas requis. « Windows only for now » reste une exigence.
RESTRICTIFS = frozenset({'uniquement', 'exclusivement', 'seulement', 'only', 'exclusively'})
RESTRICTIFS_SOUPLES = frozenset({'utilise', 'utilisee', 'utilises', 'utilisees', 'used', 'needed', 'necessaire',
                                 'required', 'requis', 'tested', 'teste', 'testee'})
USAGES_ANNEXES = frozenset({'test', 'tests', 'testing', 'developpement', 'development', 'dev', 'ci', 'benchmark',
                            'benchmarks', 'entrainement', 'training', 'debug', 'debogage', 'deploiement',
                            'deployment', 'demo', 'demonstration', 'exemples', 'examples', 'fine', 'finetuning'})
SOUPLES = frozenset({'facultatif', 'facultative', 'facultatifs', 'facultatives', 'optionnel', 'optionnelle',
                     'optionnels', 'optionnelles', 'optional', 'optionally', 'recommande', 'recommandee',
                     'recommandes', 'recommandees', 'recommended', 'conseille', 'conseillee', 'conseilles',
                     'conseillees', 'advised', 'option', 'eventuellement', 'eventuel', 'eventuelle', 'preferred',
                     'preferably', 'prefere', 'preferee', 'preferable', 'ideally', 'idealement', 'suggested',
                     'suggere', 'suggeree', 'suggeres', 'suggerees'})
SOUPLES_EXPRESSIONS = ('si disponible', 'if available', 'non requis', 'non requise', 'not required',
                       'pas obligatoire', 'pas necessaire', 'if you have', 'si necessaire', 'if needed',
                       'if necessary', 'if you need', 'if you want', 'au besoin', 'si besoin', 'si vous avez',
                       'en option', 'de preference', 'nice to have', 'si possible', 'if possible', 'if you prefer',
                       'si vous preferez', 's il est disponible', 'if present', 'when available',
                       'lorsqu il est disponible', 'quand il est disponible')
ARTEFACTS = frozenset({'workflow', 'workflows', 'noeud', 'noeuds', 'nœud', 'nœuds', 'node', 'nodes', 'plugin',
                       'plugins', 'extension', 'extensions', 'skill', 'skills', 'template', 'templates', 'gabarit',
                       'gabarits'})
# Un artefact cité pour une migration ou chez l'utilisateur n'est pas une dépendance (« importez vos workflows
# Zapier », « migrate your n8n workflows »)
MIGRATIONS = frozenset({'importez', 'importer', 'importe', 'import', 'imports', 'importing', 'migrez', 'migrer',
                        'migre', 'migrate', 'migrating', 'migration', 'depuis', 'from', 'convertir', 'convert',
                        'vos', 'votre', 'your', 'existing', 'existants', 'existantes'})
# Produit cité comme celui qu'on remplace (dans la fiche) ; « comme » et « like » seulement juste avant
MARQUES_REFERENCE = frozenset({'alternative', 'alternatives', 'remplacant', 'remplacante', 'equivalent', 'equivalente',
                               'equivalents', 'similaire', 'similaires', 'remplace', 'remplacer', 'remplacent',
                               'replace', 'replaces', 'replacement', 'substitute', 'substitut', 'remplacement',
                               'successeur', 'successor', 'versus', 'vs', 'clone', 'similar'})
# Qualifient l'identifiant sans en être une alternative (« NVIDIA or AMD GPU »)
MARQUES_MATERIEL = frozenset({'nvidia', 'amd', 'intel', 'apple', 'radeon', 'geforce', 'rtx'})
# Systèmes (formes repliées) : plusieurs dans un même élément de liste = plateformes possibles, pas une exigence
SYSTEMES = frozenset({'windows', 'linux', 'macos', 'mac', 'ubuntu', 'debian', 'osx', 'wsl', 'wsl2', 'android',
                      'ios', 'freebsd', 'fedora'})
# Exclusion : formes cherchées dans les fiches quand elles diffèrent de celles du concept (« sans Docker » n'exclut
# pas tout conteneur : Podman n'est pas Docker ; « sans GPU » : la marque NVIDIA seule, une clé d'API NVIDIA NIM,
# ne prouve pas un GPU)
FORMES_EXCLUSION = {
    'docker': ['docker', 'docker compose', 'dockerfile'],
    'gpu': ['gpu', 'gpus', 'cuda', 'vram', 'carte graphique', 'cartes graphiques', 'graphics card', 'graphics cards',
            'carte nvidia', 'cartes nvidia', 'nvidia rtx', 'geforce'],
}
# Après « pas » / « not » / « sans », ces mots ne ferment plus la négation quand l'unité suivante (articles mis à
# part) est un identifiant (« pas avec Docker », « not for Windows ») ; ailleurs, règle inchangée (FIN_NEGATION).
# La négation se referme après cet identifiant (« pas avec Docker en Python » cherche Python).
LIAISONS_EXCLUSION = frozenset({'pour', 'avec', 'sur', 'sous', 'dans', 'for', 'with', 'on', 'in'})
# Verbes que régit une négation qui ne nie pas l'objet du besoin (seulement le verbe nié : entre « ne » et « pas »,
# ou juste après « can't », « don't » ; jamais avec « sans » / « without »). Mémoire de l'utilisateur, négation
# ignorée : « I can't find the n8n workflow I saved », « je ne retrouve plus le dépôt n8n », « je ne me souviens plus
# du nom de l'outil d'OCR » ; pas « Find a web scraper without Docker » (« without » n'est pas régi par « find »)
VERBES_SANS_NEGATION = frozenset({
    'find', 'remember', 'recall', 'recollect', 'locate', 'retrieve', 'seem', 'trouve', 'retrouve', 'trouver',
    'retrouver', 'souviens', 'souvient', 'souvenir', 'rappelle', 'rappeler',
})
# Capacité ou savoir : mémoire seulement devant un interrogatif ou un verbe de mémoire (« je ne sais pas quel outil
# n8n », « je n'arrive pas à retrouver le dépôt ») ; sinon une vraie négation (« je n'arrive pas à installer Docker »,
# « je ne sais pas configurer Kubernetes » : la technologie est exclue)
VERBES_CAPACITE = frozenset({'sais', 'sait', 'savons', 'arrive', 'arrivons', 'parviens', 'parvient', 'able'})
INTERROGATIFS = frozenset({'quel', 'quelle', 'quels', 'quelles', 'lequel', 'laquelle', 'si', 'comment', 'pourquoi',
                           'which', 'what', 'where', 'whether', 'how'})
# Indifférence : les technologies de la portée sont « indifférentes » (ni cherchées ni exclues) : « doesn't matter if
# it's React or Vue », « I don't care about GPU acceleration », « I don't mind using Docker », « ça ne me dérange pas
# d'utiliser Docker », « je n'hésite pas à utiliser Docker »
VERBES_INDIFFERENCE = frozenset({'matter', 'matters', 'care', 'mind', 'importe', 'derange', 'derangent', 'gene',
                                 'genent', 'hesite', 'hesitons', 'embete', 'bother', 'bothers'})
# Verbe nié qui dit la qualité, pas l'usage : sa suite prépositionnelle est un contexte (« un éditeur qui ne plante
# jamais sous Windows », « qui ne rame pas sous Windows », « doesn't crash on Linux »)
VERBES_QUALITE = frozenset({'plante', 'plantent', 'rame', 'rament', 'crash', 'crashe', 'crashes', 'bug', 'bugue',
                            'buguent', 'freeze', 'freezes', 'gele', 'bloque', 'lag', 'lags', 'lague'})
# Entre le déclencheur et l'identifiant, seuls ces mots (repliés, outre les mots vides et les liaisons) gardent
# l'exclusion : « sans passer par n8n », « without installing Docker », « sans être obligé de passer par Docker »,
# « without needing Kubernetes » ; un autre mot l'interdit (« I'm not sure whether to use n8n », « je n'ai pas encore
# choisi entre n8n et Zapier » : n8n est seulement nié, comme tout mot nié)
VERBES_EXCLUSION = frozenset({
    'passer', 'passant', 'installer', 'installant', 'installation', 'installing', 'install', 'installed', 'needing',
    'need', 'needed', 'having', 'oblige', 'obligee', 'obliges', 'obligees', 'forced', 'forcing', 'devoir', 'besoin',
    'dependre', 'dependant', 'depending', 'depend', 'recourir', 'recours', 'relying', 'rely', 'utilisant', 'going',
    'through', 'lancer', 'lancant', 'running', 'run', 'tourner', 'deployer', 'deploying', 'deploy', 'configurer',
    'configuring', 'toucher', 'touching', 'compte', 'account', 'abonnement', 'subscription', 'payer', 'paying',
    'apprendre', 'learning', 'connaitre', 'knowing', 'exiger', 'demander', 'launching', 'launch', 'setting', 'setup',
    # permission : « I'm not allowed to install Docker », « je n'ai pas le droit d'installer Docker »
    'allowed', 'permitted', 'autorise', 'autorisee', 'autorises', 'droit',
    # « je n'ai pas envie de Kubernetes », « sans rien toucher côté Windows », « nothing that needs macOS »
    'envie', 'cote', 'rien', 'anything', 'nothing', 'needs',
})
INVARIABLES = frozenset({'cours', 'news', 'series', 'corpus', 'status', 'process', 'access', 'analysis', 'windows',
                         'pandas', 'kubernetes', 'ollama', 'ios', 'gis', 'aws', 'docs', 'sous', 'plus', 'tous',
                         'mais'})
FAUX_AMIS = {
    'btp': {'building', 'buildings', 'construction', 'construire'}, 'bim': {'building'},
    'metre': {'metrique', 'metriques', 'metric', 'metrics'},
    'plan': {'planifier', 'planifie', 'planning', 'planification'},
    'document': {'documentation'}, 'veille': {'surveillance'}, 'tts': {'synthese'},
    'qcm': {'test', 'tests', 'testing'}, 'exercice': {'test', 'tests', 'testing'},
}

GABARITS_CAS_USAGE_EN = frozenset({
    'task automation via ai agents', 'multi-agent orchestration', 'agent integration',
    'model fine-tuning', 'production deployment', 'ml experimentation',
    'web app development', 'ui prototyping', 'tech stack integration',
    'development integration', 'testing', 'business adaptation'})

GABARITS_CAS_USAGE_FR = (
    r"^automatisation (de |des )?taches? (via|par|avec|grace a) (des |les )?agents?",
    r"^orchestration multi-?agents?$",
    r"^integration (d'|des |de l')agents?$",
    r"^(ajustement fin|affinage|fine-?tuning|reglage fin) (du |des |de |de la )?modeles?$",
    r"^deploiement en production$",
    r"^experimentation (en )?(ml|apprentissage automatique|machine learning)$",
    r"^developpement d'applications? web$",
    r"^prototypage (d'|de l'|des )?(interfaces?|ui)( utilisateurs?)?$",
    r"^integration (a|dans|de) (la |une )?(stack|pile) (technique|technologique)$",
    r"^integration (du|au|dans le|en|pour le) developpement$",
    r"^tests?$",
    r"^adaptation (commerciale|metier|aux besoins (metier|de l'entreprise)|business)$",
)
