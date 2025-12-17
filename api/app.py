# Tässä on kaikki sovelluslogiikka. Flask toimii Frameworkina tälle Python-pohjaiselle API:lle. Luotu Claudella.
# Aluksi projektiin importataan käytettävät kirjastot.
from flask import Flask, request, jsonify, send_file, render_template_string
from PIL import Image, UnidentifiedImageError
import numpy as np
import psycopg2
import redis
import json
import time
import io
import os

# Luodaan Flask-sovellus
app = Flask(__name__)

# Tietokanta- ja Redis-yhteydet ympäristömuuttujista
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/notes')
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379')
APP_VERSION = os.environ.get('APP_VERSION', '1.0.0')

# Redis-yhteys (lazy loading)
redis_client = None
CACHE_KEY = "notes_cache"
CACHE_TTL = 60  # sekuntia

def get_redis():
    """Hae Redis-yhteys (lazy loading)."""
    global redis_client
    if redis_client is None:
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        except:
            pass
    return redis_client

def get_db():
    """Luo PostgreSQL-tietokantayhteys."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db(max_retries=30, delay=1):
    """Alusta tietokanta. Odota kunnes PostgreSQL on valmis."""
    for attempt in range(max_retries):
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    title TEXT,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Migraatio: lisää title-sarake jos sitä ei ole
            cur.execute("""
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                   WHERE table_name='notes' AND column_name='title') THEN
                        ALTER TABLE notes ADD COLUMN title TEXT;
                    END IF;
                END $$;
            """)
            # Muistipelin tulostaulu
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scoreboard (
                    id SERIAL PRIMARY KEY,
                    grid_size VARCHAR(10) NOT NULL,
                    name VARCHAR(20) NOT NULL,
                    time_seconds INTEGER NOT NULL,
                    moves INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            cur.close()
            conn.close()
            print(f"Tietokanta alustettu onnistuneesti (yritys {attempt + 1})")
            return True
        except psycopg2.OperationalError as e:
            print(f"Odotetaan tietokantaa... (yritys {attempt + 1}/{max_retries})")
            time.sleep(delay)
    print("Tietokantaan ei saatu yhteyttä!")
    return False

def invalidate_cache():
    """Tyhjennä Redis-välimuisti."""
    r = get_redis()
    if r:
        try:
            r.delete(CACHE_KEY)
        except:
            pass

# HEALTH CHECK
@app.route('/health')
def health():
    return "OK", 200

# VERSION
@app.route('/version')
def version():
    """Palauta sovelluksen versio."""
    return jsonify({"version": APP_VERSION})

# METRICS (Prometheus)
@app.route('/metrics')
def metrics():
    """Palauta metriikat Prometheus-muodossa."""
    # Hae muistiinpanojen määrä
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM notes")
        notes_count = cur.fetchone()[0]
        cur.close()
        conn.close()
    except:
        notes_count = 0
    
    # Prometheus tekstimuotoinen vastaus
    metrics_text = f"""# HELP notes_total Total number of notes
# TYPE notes_total gauge
notes_total {notes_count}
# HELP app_up Application is up
# TYPE app_up gauge
app_up 1
"""
    return metrics_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}

# NOTES API
@app.route('/api/notes', methods=['GET', 'POST'])
def notes():
    if request.method == 'POST':
        data = request.get_json()
        content = data.get('content', '') if data else ''
        title = data.get('title', '') if data else ''
        if not content:
            return jsonify({"error": "content vaaditaan"}), 400
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO notes (title, content) VALUES (%s, %s) RETURNING id, created_at", (title or None, content,))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        invalidate_cache()
        return jsonify({"status": "tallennettu", "id": row[0]}), 201
    else:
        # Yritä hakea välimuistista. Mikäli epäonnistuu, hae tietokannasta.
        r = get_redis()
        if r:
            try:
                cached = r.get(CACHE_KEY)
                if cached:
                    return jsonify(json.loads(cached))
            except:
                pass
        
        # Hae tietokannasta
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, title, content, created_at, updated_at FROM notes ORDER BY id DESC")
        notes_list = [{
            "id": row[0],
            "title": row[1],
            "content": row[2],
            "created_at": row[3].isoformat() + 'Z' if row[3] else None,
            "updated_at": row[4].isoformat() + 'Z' if row[4] else None
        } for row in cur.fetchall()]
        cur.close()
        conn.close()
        
        # Tallenna välimuistiin tietokannasta haettu data seuraavaa pyyntöä varten
        if r:
            try:
                r.setex(CACHE_KEY, CACHE_TTL, json.dumps(notes_list))
            except:
                pass
        return jsonify(notes_list)

@app.route('/api/notes/<int:note_id>', methods=['PUT', 'DELETE'])
def manage_note(note_id):
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == 'PUT':
        data = request.get_json()
        content = data.get('content', '') if data else ''
        if not content:
            return jsonify({"error": "content vaaditaan"}), 400
        
        cur.execute("UPDATE notes SET content = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (content, note_id))
        conn.commit()
        cur.close()
        conn.close()
        invalidate_cache()
        return jsonify({"status": "päivitetty"}), 200
    else:  # DELETE
        cur.execute("DELETE FROM notes WHERE id = %s", (note_id,))
        conn.commit()
        cur.close()
        conn.close()
        invalidate_cache()
        return jsonify({"status": "poistettu"}), 200

# MEMORY GAME REDIS API
MEMORY_REDIS_KEY = "memory_saves"

@app.route('/api/memory/save', methods=['POST'])
def memory_save():
    """Tallenna pelitila Redisiin nimellä."""
    r = get_redis()
    if not r:
        return jsonify({"error": "Redis ei käytettävissä"}), 503
    
    data = request.get_json()
    name = data.get('name', '').strip()
    state = data.get('state', {})
    
    if not name:
        return jsonify({"error": "Nimi vaaditaan"}), 400
    
    try:
        r.hset(MEMORY_REDIS_KEY, name, json.dumps(state))
        return jsonify({"status": "tallennettu", "name": name}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/memory/saves', methods=['GET'])
def memory_list_saves():
    """Listaa kaikki tallennetut pelit."""
    r = get_redis()
    if not r:
        return jsonify([])
    
    try:
        saves = r.hgetall(MEMORY_REDIS_KEY)
        result = []
        for name, state_json in saves.items():
            state = json.loads(state_json)
            result.append({
                "name": name,
                "matched": state.get("matched", 0),
                "totalPairs": state.get("totalPairs", 0),
                "moves": state.get("moves", 0)
            })
        return jsonify(result)
    except Exception as e:
        return jsonify([])

@app.route('/api/memory/load/<name>', methods=['GET'])
def memory_load(name):
    """Lataa tallennettu peli nimellä."""
    r = get_redis()
    if not r:
        return jsonify({"error": "Redis ei käytettävissä"}), 503
    
    try:
        state_json = r.hget(MEMORY_REDIS_KEY, name)
        if not state_json:
            return jsonify({"error": "Peliä ei löydy"}), 404
        return jsonify(json.loads(state_json))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/memory/delete/<name>', methods=['DELETE'])
def memory_delete(name):
    """Poista tallennettu peli."""
    r = get_redis()
    if not r:
        return jsonify({"error": "Redis ei käytettävissä"}), 503
    
    try:
        r.hdel(MEMORY_REDIS_KEY, name)
        return jsonify({"status": "poistettu"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# MEMORY GAME SCOREBOARD API (PostgreSQL)
@app.route('/api/memory/scoreboard/<grid_size>', methods=['GET'])
def get_scoreboard(grid_size):
    """Hae tulostaulu (top 10 nopeinta aikaa)."""
    if grid_size not in ['4x4', '6x6']:
        return jsonify([]), 400
    
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT name, time_seconds, moves, created_at 
            FROM scoreboard 
            WHERE grid_size = %s 
            ORDER BY time_seconds ASC 
            LIMIT 10
        """, (grid_size,))
        
        result = []
        for i, row in enumerate(cur.fetchall()):
            result.append({
                "rank": i + 1,
                "name": row[0],
                "time": row[1],
                "moves": row[2],
                "date": row[3].strftime("%d.%m.%Y") if row[3] else ""
            })
        cur.close()
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify([])

@app.route('/api/memory/scoreboard/<grid_size>', methods=['POST'])
def add_to_scoreboard(grid_size):
    """Lisää tulos tulostaululle."""
    if grid_size not in ['4x4', '6x6']:
        return jsonify({"error": "Virheellinen ruudukon koko"}), 400
    
    data = request.get_json()
    name = data.get('name', '').strip()[:20]  # Rajoita nimen pituus
    time_seconds = data.get('time', 0)
    moves = data.get('moves', 0)
    
    if not name:
        return jsonify({"error": "Nimi vaaditaan"}), 400
    if time_seconds <= 0:
        return jsonify({"error": "Virheellinen aika"}), 400
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Lisää tulos
        cur.execute("""
            INSERT INTO scoreboard (grid_size, name, time_seconds, moves) 
            VALUES (%s, %s, %s, %s)
        """, (grid_size, name, time_seconds, moves))
        conn.commit()
        
        # Tarkista sijoitus
        cur.execute("""
            SELECT COUNT(*) FROM scoreboard 
            WHERE grid_size = %s AND time_seconds < %s
        """, (grid_size, time_seconds))
        rank = cur.fetchone()[0] + 1
        
        # Pidä vain top 10 tulosta per ruudukon koko
        cur.execute("""
            DELETE FROM scoreboard WHERE id IN (
                SELECT id FROM scoreboard 
                WHERE grid_size = %s 
                ORDER BY time_seconds ASC 
                OFFSET 10
            )
        """, (grid_size,))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({
            "status": "tallennettu",
            "rank": rank
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# IMAGE API
IMAGE_FORM = """
<!DOCTYPE html>
<html lang="fi" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pikselitehoste</title>
    <style>
        :root {
            --bg-dark: #0a0f0d;
            --bg-card: #111916;
            --border: #1e2d26;
            --accent: #3ecf8e;
            --text: #e2e8e4;
            --text-dim: #8a9a8f;
            --font-mono: 'SF Mono', 'Fira Code', 'Consolas', monospace;
        }
        
        [data-theme="light"] {
            --bg-dark: #f5f7f6;
            --bg-card: #ffffff;
            --border: #d1d9d5;
            --accent: #2a9d6e;
            --text: #1a1f1c;
            --text-dim: #5a6a5f;
        }
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: var(--font-mono);
            background: var(--bg-dark);
            color: var(--text);
            min-height: 100vh;
            line-height: 1.7;
            font-size: 18px;
            transition: background 0.3s, color 0.3s;
        }
        
        .container {
            max-width: 700px;
            margin: 0 auto;
            padding: 40px 20px;
        }
        
        @media (max-width: 600px) {
            .container { padding: 20px 15px; }
            .terminal-body { padding: 20px; }
            h1 { font-size: 1.4em; }
            .subtitle { font-size: 15px; }
            .info-box { font-size: 14px; padding: 12px 15px; }
            .slider-value { font-size: 1.6em; }
            .examples { flex-direction: column; gap: 15px; font-size: 14px; }
            .btn { padding: 12px; font-size: 15px; }
        }
        
        .terminal-header {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 12px 16px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-bottom: none;
            border-radius: 8px 8px 0 0;
            transition: background 0.3s, border-color 0.3s;
        }
        .terminal-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }
        .dot-red { background: #ff5f57; }
        .dot-yellow { background: #febc2e; }
        .dot-green { background: #28c840; }
        .terminal-title {
            flex: 1;
            text-align: center;
            color: var(--text-dim);
            font-size: 16px;
        }
        
        .theme-toggle {
            background: var(--bg-dark);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 6px 10px;
            color: var(--text-dim);
            font-family: var(--font-mono);
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .theme-toggle:hover {
            border-color: var(--accent);
            color: var(--accent);
        }
        
        .terminal-body {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 0 0 8px 8px;
            padding: 30px;
            transition: background 0.3s, border-color 0.3s;
        }
        
        .back-link {
            display: inline-block;
            margin-bottom: 25px;
            color: var(--accent);
            text-decoration: none;
            font-size: 18px;
        }
        .back-link:hover { text-decoration: underline; }
        .back-link::before { content: '< '; }
        
        h1 {
            font-size: 1.8em;
            font-weight: 400;
            color: var(--text);
            margin-bottom: 10px;
            text-align: center;
        }
        h1::before { content: '# '; color: var(--accent); }
        
        .subtitle {
            color: var(--text-dim);
            font-size: 18px;
            text-align: center;
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
        }
        
        .info-box {
            background: var(--bg-dark);
            border: 1px solid var(--border);
            border-left: 3px solid var(--accent);
            padding: 15px 20px;
            border-radius: 0 6px 6px 0;
            margin-bottom: 25px;
            font-size: 17px;
            color: var(--text-dim);
            transition: background 0.3s, border-color 0.3s;
        }
        .info-box strong {
            color: var(--accent);
            display: block;
            margin-bottom: 8px;
        }
        
        .form-group { margin-bottom: 20px; }
        
        label {
            display: block;
            color: var(--accent);
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }
        label::before { content: '// '; }
        
        .file-input {
            display: none;
        }
        
        .file-label {
            display: block;
            width: 100%;
            padding: 20px;
            background: var(--bg-dark);
            border: 1px dashed var(--border);
            border-radius: 6px;
            color: var(--text-dim);
            font-family: var(--font-mono);
            font-size: 16px;
            cursor: pointer;
            transition: border-color 0.2s;
            text-align: center;
        }
        .file-label:hover { border-color: var(--accent); }
        .file-label.has-file { 
            border-color: var(--accent); 
            color: var(--accent);
        }
        
        .slider-container {
            background: var(--bg-dark);
            border: 1px solid var(--border);
            padding: 20px;
            border-radius: 6px;
            transition: background 0.3s, border-color 0.3s;
        }
        .slider-value {
            font-size: 2em;
            font-weight: 600;
            color: var(--accent);
            text-align: center;
            margin-bottom: 15px;
        }
        input[type="range"] {
            width: 100%;
            height: 6px;
            border-radius: 3px;
            background: var(--border);
            outline: none;
            -webkit-appearance: none;
        }
        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: var(--accent);
            cursor: pointer;
        }
        
        .btn {
            width: 100%;
            padding: 15px;
            background: var(--accent);
            color: var(--bg-dark);
            border: none;
            border-radius: 6px;
            font-family: var(--font-mono);
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s, transform 0.2s;
        }
        .btn:hover { 
            opacity: 0.9;
            transform: translateY(-1px);
        }
        
        .examples {
            display: flex;
            justify-content: space-around;
            margin-top: 25px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
            font-size: 15px;
            color: var(--text-dim);
        }
        .example { text-align: center; }
        .example-label {
            display: block;
            color: var(--accent);
            margin-bottom: 5px;
        }
        
        /* Top Navigation Menu */
        .top-nav {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 12px;
            padding: 12px 18px;
            background: var(--bg-card);
            border-bottom: 1px solid var(--border);
            flex-wrap: wrap;
        }
        .top-nav-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .top-nav-label {
            color: var(--text-dim);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .top-nav a {
            color: var(--text-dim);
            text-decoration: none;
            font-size: 15px;
            padding: 6px 10px;
            border-radius: 4px;
            transition: color 0.2s, background 0.2s;
        }
        .top-nav a:hover {
            color: var(--accent);
            background: rgba(62, 207, 142, 0.1);
        }
        .top-nav-divider {
            width: 1px;
            height: 20px;
            background: var(--border);
            margin: 0 10px;
        }
        .top-nav-home {
            display: flex;
            align-items: center;
            gap: 6px;
            color: var(--accent);
            text-decoration: none;
            font-size: 16px;
            font-weight: 600;
            padding: 6px 12px;
            border-radius: 4px;
            transition: background 0.2s;
        }
        .top-nav-home:hover {
            background: rgba(62, 207, 142, 0.1);
        }
        .top-nav-home svg {
            width: 24px;
            height: 24px;
        }
        @media (max-width: 500px) {
            .top-nav { padding: 10px 12px; gap: 6px; }
            .top-nav a { font-size: 12px; padding: 4px 7px; }
            .top-nav-label { font-size: 10px; }
            .top-nav-divider { display: none; }
            .top-nav-group { gap: 5px; }
            .top-nav-home { font-size: 14px; padding: 4px 8px; }
            .top-nav-home svg { width: 18px; height: 18px; }
        }
    </style>
</head>
<body>
    <nav class="top-nav">
        <a href="/" class="top-nav-home" title="Etusivu">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M13.983 11.078h2.119a.186.186 0 00.186-.185V9.006a.186.186 0 00-.186-.186h-2.119a.186.186 0 00-.185.186v1.887c0 .102.083.185.185.185m-2.954-5.43h2.118a.186.186 0 00.186-.186V3.574a.186.186 0 00-.186-.185h-2.118a.186.186 0 00-.185.185v1.888c0 .102.082.185.185.186m0 2.716h2.118a.187.187 0 00.186-.186V6.29a.186.186 0 00-.186-.185h-2.118a.186.186 0 00-.185.185v1.887c0 .102.082.186.185.186m-2.93 0h2.12a.186.186 0 00.184-.186V6.29a.185.185 0 00-.185-.185H8.1a.185.185 0 00-.185.185v1.887c0 .102.083.186.185.186m-2.964 0h2.119a.186.186 0 00.185-.186V6.29a.186.186 0 00-.185-.185H5.136a.186.186 0 00-.186.185v1.887c0 .102.084.186.186.186m5.893 2.715h2.118a.186.186 0 00.186-.185V9.006a.186.186 0 00-.186-.186h-2.118a.186.186 0 00-.185.186v1.887c0 .102.082.185.185.185m-2.93 0h2.12a.185.185 0 00.184-.185V9.006a.185.185 0 00-.184-.186h-2.12a.185.185 0 00-.184.186v1.887c0 .102.083.185.185.185m-2.964 0h2.119a.185.185 0 00.185-.185V9.006a.185.185 0 00-.185-.186h-2.119a.185.185 0 00-.186.186v1.887c0 .102.084.185.186.185m-2.92 0h2.12a.185.185 0 00.184-.185V9.006a.185.185 0 00-.184-.186h-2.12a.186.186 0 00-.185.186v1.887c0 .102.083.185.185.185M23.763 9.89c-.065-.051-.672-.51-1.954-.51-.338.001-.676.03-1.01.087-.248-1.7-1.653-2.53-1.716-2.566l-.344-.199-.226.327c-.284.438-.49.922-.612 1.43-.23.97-.09 1.882.403 2.661-.595.332-1.55.413-1.744.42H.751a.751.751 0 00-.75.748 11.376 11.376 0 00.692 4.062c.545 1.428 1.355 2.48 2.41 3.124 1.18.723 3.1 1.137 5.275 1.137.983.003 1.963-.086 2.93-.266a12.248 12.248 0 003.823-1.389c.98-.567 1.86-1.288 2.61-2.136 1.252-1.418 1.998-2.997 2.553-4.4h.221c1.372 0 2.215-.549 2.68-1.009.309-.293.55-.65.707-1.046l.098-.288z"/></svg>
        </a>
        <div class="top-nav-divider"></div>
        <div class="top-nav-group">
            <span class="top-nav-label">Tietoa:</span>
            <a href="/arkkitehtuuri.html">Arkkitehtuuri</a>
            <a href="/docker.html">Docker</a>
            <a href="/compose.html">Compose</a>
        </div>
        <div class="top-nav-divider"></div>
        <div class="top-nav-group">
            <span class="top-nav-label">Sovellukset:</span>
            <a href="/notes.html">Muistiinpanot</a>
            <a href="/muistipeli.html">Muistipeli</a>
            <a href="/api/image">Kuvatyökalu</a>
        </div>
    </nav>
    <div class="container">
        <div class="terminal-header">
            <div class="terminal-dot dot-red"></div>
            <div class="terminal-dot dot-yellow"></div>
            <div class="terminal-dot dot-green"></div>
            <span class="terminal-title">kuvatyökalu ~ terminaali</span>
            <button class="theme-toggle" onclick="toggleTheme()">teema</button>
        </div>
        
        <div class="terminal-body">
            <a href="/" class="back-link">takaisin</a>
            
            <h1>Pikselitehoste</h1>
            <p class="subtitle" style="white-space: pre-line;">Luo kuvia pikselihajotuksella.
                Tässä työkalussa voit ladata kuvan ja valita kuinka suuri osa pikseleistä näytetään valitsemassasi kuvassa.

                Tämä työkalu havainnollistaa pikseleiden merkitystä kuvan muodostumisessa.
                Mitä jos osa pikseleistä puuttuisi? Kuinka paljon tietoa tarvitaan, jotta kuva on tunnistettavissa?
                Kokeile eri prosentteja ja katso miten kuva muuttuu. Voit tutkia, miten paljon pikseleitä tarvitaan erilaisten objektien tunnistamiseen kuvasta.
            </p>
            
            <div class="info-box">
                <strong>Lyhyesti: Miten tämä toimii?</strong>
                Lataa kuva ja valitse kuinka suuri osa pikseleistä näytetään. 
                Pienempi prosentti = abstraktimpi tulos. Loput pikselit muuttuvat mustiksi.
            </div>
            
            <form method="POST" enctype="multipart/form-data">
                <div class="form-group">
                    <label>Valitse kuva</label>
                    <label class="file-label" id="fileLabel">
                        Ei valittua tiedostoa - klikkaa valitaksesi
                        <input type="file" name="image" accept="image/*" required class="file-input" id="fileInput" onchange="updateFileName(this)">
                    </label>
                </div>
                
                <div class="form-group">
                    <label>Näkyvien pikselien osuus</label>
                    <div class="slider-container">
                        <div class="slider-value"><span id="val">50</span>%</div>
                        <input type="range" name="percentage" min="1" max="100" value="50" 
                               oninput="document.getElementById('val').textContent=this.value">
                    </div>
                </div>
                
                <button type="submit" class="btn">Luo kuva</button>
            </form>
            
            <div class="examples">
                <div class="example">
                    <span class="example-label">10%</span>
                    Abstrakti
                </div>
                <div class="example">
                    <span class="example-label">50%</span>
                    Puolet tiedosta jäljellä
                </div>
                <div class="example">
                    <span class="example-label">90%</span>
                    Lähes alkuperäinen
                </div>
            </div>
        </div>
    </div>
    
    <script>
        function toggleTheme() {
            const html = document.documentElement;
            const current = html.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
        }
        
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme) {
            document.documentElement.setAttribute('data-theme', savedTheme);
        }
        
        function updateFileName(input) {
            const label = document.getElementById('fileLabel');
            if (input.files && input.files[0]) {
                label.textContent = input.files[0].name;
                label.classList.add('has-file');
                label.appendChild(input);
            }
        }
    </script>
</body>
</html>
"""

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/image', methods=['GET', 'POST'])
def process_image():
    if request.method == 'GET':
        return render_template_string(IMAGE_FORM)

    file = request.files.get('image')
    if not file or not allowed_file(file.filename):
        return "Virhe: vain kuvatiedostot sallittu (PNG/JPG/JPEG/GIF/WEBP).", 400

    try:
        percentage = int(request.form.get('percentage', 50))
        percentage = max(1, min(100, percentage))
    except ValueError:
        percentage = 50

    try:
        img = Image.open(file).convert("RGB")
    except UnidentifiedImageError:
        return "Virhe: tiedosto ei ole kelvollinen kuva.", 400

    arr = np.array(img)
    total_pixels = arr.shape[0] * arr.shape[1]
    keep_pixels = max(1, int(total_pixels * (percentage / 100)))

    # Valitaan satunnaisesti säilytettävät pikselit
    mask = np.zeros(total_pixels, dtype=bool)
    mask[:keep_pixels] = True
    np.random.shuffle(mask)
    mask = mask.reshape(arr.shape[0], arr.shape[1])

    # Musta tausta, säilytä valitut pikselit
    output_arr = np.zeros_like(arr)
    output_arr[mask] = arr[mask]

    output_img = Image.fromarray(output_arr)
    output = io.BytesIO()
    output_img.save(output, format="PNG")
    output.seek(0)

    return send_file(output, mimetype="image/png", download_name="muokattu.png")

if __name__ == "__main__":
    init_db()  # Alusta tietokanta käynnistyksessä
    app.run(host="0.0.0.0", port=5000)
