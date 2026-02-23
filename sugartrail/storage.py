from pathlib import Path
import sqlite3
import json


SCHEMA = """
CREATE TABLE IF NOT EXISTS networks (
    network_id INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_type TEXT,
    seed_value TEXT,
    n INTEGER NOT NULL DEFAULT 0,
    link_type TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS network_hops (
    network_id INTEGER NOT NULL,
    hop_number INTEGER NOT NULL,
    hop_config_json TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (network_id, hop_number),
    FOREIGN KEY (network_id) REFERENCES networks(network_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    title TEXT,
    lat REAL,
    lon REAL
);

CREATE TABLE IF NOT EXISTS network_nodes (
    network_id INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    depth INTEGER NOT NULL,
    PRIMARY KEY (network_id, node_id),
    FOREIGN KEY (network_id) REFERENCES networks(network_id) ON DELETE CASCADE,
    FOREIGN KEY (node_id) REFERENCES nodes(node_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS edges (
    network_id INTEGER NOT NULL,
    end_node_id TEXT NOT NULL,
    start_node_id TEXT NOT NULL,
    arc_type TEXT NOT NULL,
    PRIMARY KEY (network_id, end_node_id, start_node_id, arc_type),
    FOREIGN KEY (network_id) REFERENCES networks(network_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS address_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_number TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    start_date TEXT,
    end_date TEXT,
    lat REAL,
    lon REAL
);

CREATE TABLE IF NOT EXISTS company_records (
    company_number TEXT PRIMARY KEY,
    record_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS maxsize_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    network_id INTEGER NOT NULL,
    node_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    maxsize_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    UNIQUE(network_id, node_id, maxsize_type),
    FOREIGN KEY (network_id) REFERENCES networks(network_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expanded_nodes (
    node_id TEXT PRIMARY KEY
);

CREATE INDEX IF NOT EXISTS idx_network_nodes_depth
    ON network_nodes(network_id, depth);
CREATE INDEX IF NOT EXISTS idx_nodes_type
    ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_edges_end
    ON edges(network_id, end_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_start
    ON edges(network_id, start_node_id);
CREATE INDEX IF NOT EXISTS idx_address_history_company
    ON address_history(company_number);
CREATE UNIQUE INDEX IF NOT EXISTS idx_address_history_unique
    ON address_history(company_number, address, COALESCE(start_date, ''));
"""

def get_default_path():
    return Path(__file__).parent.parent / "sugartrail_networks.db"

class SQLiteStore:
    """SQLite-backed storage for network graph state."""

    def __init__(self, db_path=None):
        self.db_path = db_path or get_default_path()
        self._conn = None
        self._ensure_schema()

    @property
    def conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _ensure_schema(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def commit(self):
        self.conn.commit()

    def begin(self):
        self.conn.execute("BEGIN IMMEDIATE")

    # -- Network management --

    def create_network(self, seed_type, seed_value):
        cur = self.conn.execute(
            "INSERT INTO networks (seed_type, seed_value) VALUES (?, ?)",
            (seed_type, seed_value),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_network_depth(self, network_id):
        row = self.conn.execute(
            "SELECT n FROM networks WHERE network_id = ?", (network_id,)
        ).fetchone()
        return row['n'] if row else 0

    def set_network_depth(self, network_id, n):
        self.conn.execute(
            "UPDATE networks SET n = ?, updated_at = datetime('now') WHERE network_id = ?",
            (n, network_id),
        )

    def set_network_link_type(self, network_id, link_type):
        self.conn.execute(
            "UPDATE networks SET link_type = ? WHERE network_id = ?",
            (link_type, network_id),
        )

    def get_network_link_type(self, network_id):
        row = self.conn.execute(
            "SELECT link_type FROM networks WHERE network_id = ?", (network_id,)
        ).fetchone()
        return row['link_type'] if row else None

    def save_hop(self, network_id, hop_number, hop_config):
        self.conn.execute(
            "INSERT OR REPLACE INTO network_hops (network_id, hop_number, hop_config_json) VALUES (?, ?, ?)",
            (network_id, hop_number, json.dumps(hop_config)),
        )

    def get_hop_history(self, network_id):
        rows = self.conn.execute(
            "SELECT hop_config_json FROM network_hops WHERE network_id = ? ORDER BY hop_number",
            (network_id,),
        ).fetchall()
        return [json.loads(r['hop_config_json']) for r in rows]

    # -- Node management --

    def ensure_node(self, node_id, node_type, title=None, lat=None, lon=None):
        self.conn.execute(
            """INSERT INTO nodes (node_id, node_type, title, lat, lon)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(node_id) DO UPDATE SET
                 title = COALESCE(excluded.title, nodes.title),
                 lat = COALESCE(excluded.lat, nodes.lat),
                 lon = COALESCE(excluded.lon, nodes.lon)""",
            (node_id, node_type, title, lat, lon),
        )

    def ensure_network_node(self, network_id, node_id, depth):
        self.conn.execute(
            "INSERT OR IGNORE INTO network_nodes (network_id, node_id, depth) VALUES (?, ?, ?)",
            (network_id, node_id, depth),
        )

    def node_in_network(self, network_id, node_id):
        row = self.conn.execute(
            "SELECT 1 FROM network_nodes WHERE network_id = ? AND node_id = ?",
            (network_id, node_id),
        ).fetchone()
        return row is not None

    def get_node(self, network_id, node_id):
        row = self.conn.execute(
            """SELECT n.node_id, n.node_type, n.title, n.lat, n.lon, nn.depth
               FROM nodes n
               JOIN network_nodes nn ON nn.node_id = n.node_id
               WHERE nn.network_id = ? AND n.node_id = ?""",
            (network_id, node_id),
        ).fetchone()
        if not row:
            return None
        node = dict(row)
        arcs = self.get_arcs(network_id, node_id)
        node['arcs'] = arcs
        return node

    def get_node_depth(self, network_id, node_id):
        row = self.conn.execute(
            "SELECT depth FROM network_nodes WHERE network_id = ? AND node_id = ?",
            (network_id, node_id),
        ).fetchone()
        return row['depth'] if row else None

    def get_nodes_at_depth(self, network_id, depth, node_type=None):
        if node_type:
            rows = self.conn.execute(
                """SELECT nn.node_id FROM network_nodes nn
                   JOIN nodes n ON n.node_id = nn.node_id
                   WHERE nn.network_id = ? AND nn.depth = ? AND n.node_type = ?""",
                (network_id, depth, node_type),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT node_id FROM network_nodes WHERE network_id = ? AND depth = ?",
                (network_id, depth),
            ).fetchall()
        return [r['node_id'] for r in rows]

    def get_all_node_ids(self, network_id):
        rows = self.conn.execute(
            "SELECT node_id FROM network_nodes WHERE network_id = ?",
            (network_id,),
        ).fetchall()
        return [r['node_id'] for r in rows]

    def count_nodes(self, network_id):
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM network_nodes WHERE network_id = ?",
            (network_id,),
        ).fetchone()
        return row['cnt']

    def get_all_nodes_by_type(self, network_id, node_type):
        rows = self.conn.execute(
            """SELECT n.node_id, n.node_type, n.title, n.lat, n.lon, nn.depth
               FROM nodes n
               JOIN network_nodes nn ON nn.node_id = n.node_id
               WHERE nn.network_id = ? AND n.node_type = ?""",
            (network_id, node_type),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_node_coords(self, node_id, lat, lon):
        self.conn.execute(
            "UPDATE nodes SET lat = ?, lon = ? WHERE node_id = ?",
            (lat, lon, node_id),
        )

    # -- Edge management --

    def add_edge(self, network_id, end_node_id, start_node_id, arc_type):
        self.conn.execute(
            "INSERT OR IGNORE INTO edges (network_id, end_node_id, start_node_id, arc_type) VALUES (?, ?, ?, ?)",
            (network_id, end_node_id, start_node_id, arc_type),
        )

    def get_arcs(self, network_id, node_id):
        rows = self.conn.execute(
            "SELECT arc_type, start_node_id FROM edges WHERE network_id = ? AND end_node_id = ?",
            (network_id, node_id),
        ).fetchall()
        return [{'arc_type': r['arc_type'], 'start_node': r['start_node_id']} for r in rows]

    # -- Address history --

    def add_address_history(self, company_number, address, start_date=None, end_date=None, lat=None, lon=None):
        self.conn.execute(
            """INSERT OR IGNORE INTO address_history (company_number, address, start_date, end_date, lat, lon)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (company_number, address or '', start_date, end_date, lat, lon),
        )

    def get_address_history_for_network(self, network_id):
        rows = self.conn.execute(
            """SELECT ah.company_number, ah.address, ah.start_date, ah.end_date, ah.lat, ah.lon
               FROM address_history ah
               JOIN network_nodes nn ON nn.node_id = ah.company_number
               WHERE nn.network_id = ?""",
            (network_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_address_history_for_company(self, company_number):
        rows = self.conn.execute(
            "SELECT * FROM address_history WHERE company_number = ?",
            (company_number,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_address_history_coords(self, company_number, address, lat, lon):
        self.conn.execute(
            "UPDATE address_history SET lat = ?, lon = ? WHERE company_number = ? AND address = ?",
            (lat, lon, company_number, address),
        )

    # -- Company records --

    def upsert_company_record(self, company_number, record):
        self.conn.execute(
            "INSERT OR REPLACE INTO company_records (company_number, record_json) VALUES (?, ?)",
            (company_number, json.dumps(record)),
        )

    def get_company_record(self, company_number):
        row = self.conn.execute(
            "SELECT record_json FROM company_records WHERE company_number = ?",
            (company_number,),
        ).fetchone()
        return json.loads(row['record_json']) if row else None

    def get_company_records_for_network(self, network_id):
        rows = self.conn.execute(
            """SELECT cr.record_json FROM company_records cr
               JOIN network_nodes nn ON nn.node_id = cr.company_number
               WHERE nn.network_id = ?""",
            (network_id,),
        ).fetchall()
        return [json.loads(r['record_json']) for r in rows]

    # -- Maxsize entities --

    def add_maxsize_entity(self, network_id, node_id, entity_type, maxsize_type, size):
        self.conn.execute(
            """INSERT OR REPLACE INTO maxsize_entities (network_id, node_id, entity_type, maxsize_type, size)
               VALUES (?, ?, ?, ?, ?)""",
            (network_id, node_id, entity_type, maxsize_type, size),
        )

    def get_maxsize_entities(self, network_id):
        rows = self.conn.execute(
            "SELECT node_id, entity_type, maxsize_type, size FROM maxsize_entities WHERE network_id = ?",
            (network_id,),
        ).fetchall()
        return [{'node': r['node_id'], 'type': r['entity_type'], 'maxsize_type': r['maxsize_type'], 'size': r['size']} for r in rows]

    # -- Expanded nodes tracking --

    def mark_node_expanded(self, node_id):
        self.conn.execute(
            "INSERT OR IGNORE INTO expanded_nodes (node_id) VALUES (?)",
            (node_id,),
        )

    def is_node_expanded(self, node_id):
        row = self.conn.execute(
            "SELECT 1 FROM expanded_nodes WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        return row is not None

    def get_global_node(self, node_id):
        row = self.conn.execute(
            "SELECT node_id, node_type, title, lat, lon FROM nodes WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_edges_from_source_any_network(self, source_node_id):
        """Get all unique edges originating from a source node across all networks."""
        rows = self.conn.execute(
            "SELECT DISTINCT end_node_id, arc_type FROM edges WHERE start_node_id = ?",
            (source_node_id,),
        ).fetchall()
        return [{'end_node_id': r['end_node_id'], 'arc_type': r['arc_type']} for r in rows]

    def get_maxsize_for_node_any_network(self, node_id):
        rows = self.conn.execute(
            "SELECT DISTINCT entity_type, maxsize_type, size FROM maxsize_entities WHERE node_id = ?",
            (node_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Cross-network queries --

    def intersect_networks(self, network_id_a, network_id_b):
        rows = self.conn.execute(
            """SELECT a.node_id, a.depth + b.depth AS depth_sum
               FROM network_nodes a
               JOIN network_nodes b ON b.node_id = a.node_id
               WHERE a.network_id = ? AND b.network_id = ?
               ORDER BY depth_sum ASC""",
            (network_id_a, network_id_b),
        ).fetchall()
        return [(r['node_id'], r['depth_sum']) for r in rows]

    # -- JSON import/export --

    def import_network_json(self, data):
        seed_type = None
        seed_value = None
        if data.get('_officer_id'):
            seed_type, seed_value = 'Person', data['_officer_id']
        elif data.get('_company_id'):
            seed_type, seed_value = 'Company', data['_company_id']
        elif data.get('_address'):
            seed_type, seed_value = 'Address', data['_address']

        network_id = self.create_network(seed_type, seed_value)
        n = data.get('n', 0)
        self.set_network_depth(network_id, n)
        if data.get('link_type'):
            self.set_network_link_type(network_id, data['link_type'])

        graph = data.get('graph', {})
        for node_id, node_data in graph.items():
            self.ensure_node(
                node_id, node_data['node_type'], node_data.get('title'),
                node_data.get('lat'), node_data.get('lon'),
            )
            self.ensure_network_node(network_id, node_id, node_data['depth'])
            for arc in node_data.get('arcs', []):
                self.add_edge(network_id, node_id, arc['start_node'], arc['arc_type'])

        for entry in data.get('address_history', []):
            self.add_address_history(
                entry['company_number'], entry.get('address', ''),
                entry.get('start_date'), entry.get('end_date'),
                entry.get('lat') or None, entry.get('lon') or None,
            )

        for record in data.get('company_records', []):
            if 'company_number' in record:
                self.upsert_company_record(record['company_number'], record)

        for entity in data.get('maxsize_entities', []):
            self.add_maxsize_entity(
                network_id, entity['node'], entity['type'],
                entity['maxsize_type'], entity['size'],
            )

        for i, hop_config in enumerate(data.get('hop_history', [])):
            self.save_hop(network_id, i + 1, hop_config)

        self.conn.commit()
        return network_id

    def export_network_json(self, network_id):
        net = self.conn.execute(
            "SELECT * FROM networks WHERE network_id = ?", (network_id,)
        ).fetchone()
        if not net:
            return None

        graph = {}
        rows = self.conn.execute(
            """SELECT n.node_id, n.node_type, n.title, n.lat, n.lon, nn.depth
               FROM nodes n
               JOIN network_nodes nn ON nn.node_id = n.node_id
               WHERE nn.network_id = ?""",
            (network_id,),
        ).fetchall()
        for r in rows:
            node = {'depth': r['depth'], 'title': r['title'], 'node_type': r['node_type'], 'arcs': []}
            if r['lat'] is not None:
                node['lat'] = r['lat']
            if r['lon'] is not None:
                node['lon'] = r['lon']
            graph[r['node_id']] = node

        edge_rows = self.conn.execute(
            "SELECT end_node_id, start_node_id, arc_type FROM edges WHERE network_id = ?",
            (network_id,),
        ).fetchall()
        for e in edge_rows:
            if e['end_node_id'] in graph:
                graph[e['end_node_id']]['arcs'].append({
                    'arc_type': e['arc_type'], 'start_node': e['start_node_id']
                })

        seed_type = net['seed_type']
        return {
            'graph': graph,
            'company_records': self.get_company_records_for_network(network_id),
            'address_history': self.get_address_history_for_network(network_id),
            '_officer_id': net['seed_value'] if seed_type == 'Person' else None,
            '_company_id': net['seed_value'] if seed_type == 'Company' else None,
            '_address': net['seed_value'] if seed_type == 'Address' else None,
            'n': net['n'],
            'link_type': net['link_type'],
            'hop_history': self.get_hop_history(network_id),
            'maxsize_entities': self.get_maxsize_entities(network_id),
        }

    def delete_network(self, network_id):
        self.conn.execute("DELETE FROM networks WHERE network_id = ?", (network_id,))
        self.conn.commit()


class GraphProxy:
    """Dict-like read interface over SQLite-backed graph data.

    Supports the subset of dict operations used by the codebase:
    ``in``, ``[]``, ``keys()``, ``items()``, ``len()``, iteration.
    Write via ``__setitem__`` is supported for backward compatibility.
    """

    def __init__(self, store, network_id):
        self._store = store
        self._network_id = network_id

    def __contains__(self, node_id):
        return self._store.node_in_network(self._network_id, node_id)

    def __getitem__(self, node_id):
        node = self._store.get_node(self._network_id, node_id)
        if node is None:
            raise KeyError(node_id)
        return node

    def __setitem__(self, node_id, value):
        self._store.ensure_node(
            node_id, value['node_type'], value.get('title'),
            value.get('lat'), value.get('lon'),
        )
        self._store.ensure_network_node(self._network_id, node_id, value['depth'])
        for arc in value.get('arcs', []):
            self._store.add_edge(self._network_id, node_id, arc['start_node'], arc['arc_type'])

    def keys(self):
        return self._store.get_all_node_ids(self._network_id)

    def items(self):
        for node_id in self.keys():
            yield node_id, self[node_id]

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        return self._store.count_nodes(self._network_id)


_default_store = None


def get_store(db_path=None):
    global _default_store
    if _default_store is None or _default_store.db_path != db_path:
        _default_store = SQLiteStore(db_path)
    return _default_store
