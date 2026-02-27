# LightML – Model Registry & Evaluation Database

LightML è un sistema leggero per:

* Registrare modelli
* Collegare checkpoint a esperimenti
* Salvare metriche strutturate
* Esportare report Excel dinamicamente dal database

Tutto è basato su SQLite.
Nessun JSON manuale. Nessuna configurazione statica.

---

# 🧠 Architettura

Il sistema è organizzato attorno a 4 entità principali:

## 1️⃣ Run (Esperimento)

Rappresenta un esperimento completo.

Ogni modello vive dentro una run.

Tabella:

```sql
run (
    id INTEGER PRIMARY KEY,
    run_name TEXT UNIQUE,
    description TEXT,
    metadata TEXT
)
```

---

## 2️⃣ Model

Un modello registrato in una run.

Supporta parent-child relationship.

Tabella:

```sql
model (
    id INTEGER PRIMARY KEY,
    model_name TEXT,
    path TEXT,
    parent_id INTEGER,
    run_id INTEGER
)
```

* `parent_id` → lineage tra modelli
* `run_id` → scope dell’esperimento

---

## 3️⃣ Checkpoint

Checkpoint intermedi collegati a un modello.

Tabella:

```sql
checkpoint (
    id INTEGER PRIMARY KEY,
    model_id INTEGER,
    step INTEGER,
    path TEXT,
    created_at TEXT
)
```

Ogni checkpoint è sempre legato a un modello.

---

## 4️⃣ Metrics

Metriche associate a:

* un modello finale
* oppure un checkpoint

Tabella:

```sql
metrics (
    id INTEGER PRIMARY KEY,
    model_id INTEGER,
    checkpoint_id INTEGER,
    family TEXT,
    metric_name TEXT,
    value REAL
)
```

Vincolo logico:

* O `model_id`
* O `checkpoint_id`
* Mai entrambi

---

# 🔄 Flusso Tipico

## 1️⃣ Inizializzazione Registry

```python
initialize_registry(registry_config)
```

Crea il database SQLite e le tabelle.

---

## 2️⃣ Creazione Esperimento

```python
handle = LightMLHandle(
    db="miia_registry/main.db",
    run_name="MIIA-GAD-V1"
)
```

Crea la run se non esiste.

---

## 3️⃣ Registrazione Modello

```python
handle.register_model(
    model_name="MIIA-GAD-V1",
    path="/path/to/model",
    parent_name="MIIA-ECCOLO2"
)
```

✔ Inserisce nel DB
✔ Restituisce model_id reale (via `lastrowid`)
✔ Crea symlink nel registry

---

## 4️⃣ Registrazione Checkpoint

```python
ckpt_id = handle.register_checkpoint(
    model_name="MIIA-GAD-V1",
    step=1000,
    path="/path/to/ckpt"
)
```

✔ Inserisce checkpoint
✔ Restituisce checkpoint_id reale

---

## 5️⃣ Logging Metriche

### Su modello finale

```python
handle.log_model_metric(
    model_name="MIIA-GAD-V1",
    family="custom",
    metric_name="GENERIC ITA",
    value=76.4
)
```

### Su checkpoint

```python
handle.log_checkpoint_metric(
    checkpoint_id=ckpt_id,
    family="custom",
    metric_name="GENERIC ITA",
    value=64.1
)
```

---

# 📊 Export Excel Dinamico

Il sistema genera Excel direttamente dal database.

Non usa JSON.
Non usa configurazioni statiche.

## Caratteristiche

* 1 foglio per ogni `family`
* Colonne generate dinamicamente dalle metriche
* Righe:

  * Modelli (Phase = F)
  * Checkpoint (Phase = S)
* Formattazione automatica con color scale

---

## Esecuzione

```bash
python lightml/export.py --db miia_registry/main.db
```

Oppure:

```bash
python lightml/export.py \
    --db miia_registry/main.db \
    --output report/my_report.xlsx
```

Output default:

```
report/main_report_YYYY-MM-DD.xlsx
```

---

# 🔗 Symlink Registry

Quando registri un modello viene creato automaticamente:

```
registry/models/<run_name>__<model_name>
```

Questo permette:

* navigazione veloce
* accesso diretto ai modelli finali
* separazione netta dai checkpoint

I checkpoint NON creano symlink.

---

# 🧩 Design Principles

✔ SQLite come single source of truth
✔ Nessun hardcoding di metriche
✔ Export completamente dinamico
✔ Supporto a famiglie di metriche arbitrarie
✔ Lineage dei modelli tramite parent_id
✔ Esperimenti isolati tramite run

---

# 🚨 Errori Comuni

### Tutte le metriche finiscono sullo stesso checkpoint

Causa:

```python
return 1
```

Soluzione:

```python
cursor = conn.execute(...)
return cursor.lastrowid
```

---

### Excel con un solo foglio

Causa:

* Una sola family nel DB

L'export crea un foglio per ogni family trovata.

---

# 📁 Struttura Progetto

```
lightml/
│
├── database.py
├── registry.py
├── checkpoints.py
├── metrics.py
├── handle.py
├── export.py
│
└── tests/
```

# 🔮 Estensioni Future

Possibili miglioramenti:

* Aggregazione automatica metriche duplicate
* Filtro automatico Phase=F
* Sheet Overview aggregato
* Export CSV
* Dashboard web
* API REST

---

# ✅ Stato Attuale

* Registry funzionante
* Run isolation corretta
* Checkpoint correttamente collegati
* Metriche distribuite correttamente
* Export Excel completamente dinamico

