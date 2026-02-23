import sugartrail
import IPython
import json
import functools

from sugartrail.storage import GraphProxy, get_store


class Network:
    _unserialisable_attributes = ['hop', '_file', 'progress', '_store', '_network_id']

    """Class represents a network of connected companies, officers and
    addresses. Class contains methods to build network of user defined size from
    a single seed company, officer or address."""
    def __init__(self, officer_id=None, company_id=None, address=None, file=None, store=None):
        self._store = store or get_store()
        self._network_id = None
        self._node_cache = set()
        self._officer_id = None
        self._company_id = None
        self._address = None
        self.n = 0
        self.hop = sugartrail.hop.Hop()
        self.hop_history = []
        self.progress = sugartrail.progress.Progress()
        self._file = self.load(file)
        if not file:
            self.initialise_node(officer_id, company_id, address, file)

    def _ensure_network(self, seed_type, seed_value):
        """Create a network row in the DB if one doesn't exist yet."""
        if self._network_id is None:
            self._network_id = self._store.create_network(seed_type, seed_value)

    @property
    def graph(self):
        """Dict-like proxy over SQLite-backed graph data."""
        if self._network_id is None:
            return {}
        return GraphProxy(self._store, self._network_id)

    @graph.setter
    def graph(self, value):
        """Support assigning a dict to graph for backward compatibility."""
        if isinstance(value, dict) and value:
            for node_id, node_data in value.items():
                self._store.ensure_node(
                    node_id, node_data['node_type'], node_data.get('title'),
                    node_data.get('lat'), node_data.get('lon'),
                )
                self._store.ensure_network_node(self._network_id, node_id, node_data['depth'])
                for arc in node_data.get('arcs', []):
                    self._store.add_edge(self._network_id, node_id, arc['start_node'], arc['arc_type'])
            self._store.commit()

    def add_node(self, node_id, node_type, title, source_id=None, arc_type=None):
        """Add a node to the network and optionally link it to a source node.

        Uses _node_cache to avoid SQL round-trips: if the node is already known,
        it was discovered at an earlier depth so we skip the edge. New nodes get
        depth n+1 and the edge is added.
        """
        is_new = node_id not in self._node_cache
        self._store.ensure_node(node_id, node_type, title)
        self._store.ensure_network_node(self._network_id, node_id, self.n + 1)
        if is_new:
            self._node_cache.add(node_id)
            if source_id and arc_type:
                self._store.add_edge(self._network_id, node_id, source_id, arc_type)

    def add_seed_node(self, node_id, node_type, title):
        """Add the seed (depth 0) node for this network."""
        self._store.ensure_node(node_id, node_type, title)
        self._store.ensure_network_node(self._network_id, node_id, 0)
        self._node_cache.add(node_id)
        self._store.commit()

    def add_address_history_entry(self, entry):
        """Add an address history entry to the store."""
        self._store.add_address_history(
            entry['company_number'], entry.get('address', ''),
            entry.get('start_date'), entry.get('end_date'),
            entry.get('lat') or None, entry.get('lon') or None,
        )

    def add_maxsize_entity(self, node_id, entity_type, maxsize_type, size):
        """Record that an entity exceeded the maxsize limit."""
        self._store.add_maxsize_entity(self._network_id, node_id, entity_type, maxsize_type, size)

    @property
    def address_history(self):
        """Address history entries for companies in this network."""
        if self._network_id is None:
            return []
        return self._store.get_address_history_for_network(self._network_id)

    @address_history.setter
    def address_history(self, value):
        pass

    @property
    def company_records(self):
        """Company records for companies in this network."""
        if self._network_id is None:
            return []
        return self._store.get_company_records_for_network(self._network_id)

    @company_records.setter
    def company_records(self, value):
        pass

    @property
    def maxsize_entities(self):
        if self._network_id is None:
            return []
        return self._store.get_maxsize_entities(self._network_id)

    @maxsize_entities.setter
    def maxsize_entities(self, value):
        pass

    @property
    def officer_id(self):
        """officer_id property representing seed officer."""
        return self._officer_id

    @officer_id.setter
    @sugartrail.api.auth
    def officer_id(self, new_value):
        """officer_id setter that checks if officer_id exists in Companies House before setting value."""
        officer_info = sugartrail.api.get_appointments(new_value)
        if officer_info:
            self._officer_id = new_value
            self._ensure_network('Person', new_value)
            self.add_seed_node(new_value, 'Person', officer_info['items'][0]['name'])
        else:
            print(f"Officer with ID:{str(new_value)} not found")
            self._officer_id = None

    @property
    def officer_ids(self):
        """Get all officers from graph."""
        if self._network_id is None:
            return []
        nodes = self._store.get_all_nodes_by_type(self._network_id, 'Person')
        officer_table = []
        for node in nodes:
            arcs = self._store.get_arcs(self._network_id, node['node_id'])
            officer = {
                "officer_id": node['node_id'],
                "title": node['title'],
                "depth": node['depth'],
                'link_type': '',
                'link': ''
            }
            if not arcs:
                officer_table.append(officer)
            else:
                for arc in arcs:
                    entry = dict(officer)
                    entry['link_type'] = arc['arc_type']
                    entry['link'] = arc['start_node']
                    officer_table.append(entry)
        return officer_table

    @property
    def company_id(self):
        """company_id property representing seed company."""
        return self._company_id

    @company_id.setter
    @sugartrail.api.auth
    def company_id(self, new_value):
        """company_id setter that checks if company_id exists in Companies House before setting value."""
        company_info = sugartrail.api.get_company(new_value)
        if company_info:
            self._company_id = new_value
            self._ensure_network('Company', new_value)
            self.add_seed_node(new_value, 'Company', company_info['company_name'])
        else:
            print(f"Company with ID:{str(new_value)} not found")
            self._company_id = None

    @property
    def company_ids(self):
        if self._network_id is None:
            return []
        nodes = self._store.get_all_nodes_by_type(self._network_id, 'Company')
        company_table = []
        for node in nodes:
            arcs = self._store.get_arcs(self._network_id, node['node_id'])
            company = {
                "company_id": node['node_id'],
                "title": node['title'],
                "depth": node['depth'],
                'link_type': '',
                'link': ''
            }
            if not arcs:
                company_table.append(company)
            else:
                for arc in arcs:
                    entry = dict(company)
                    entry['link_type'] = arc['arc_type']
                    entry['link'] = arc['start_node']
                    company_table.append(entry)
        return company_table

    @property
    def address(self):
        """address property representing seed address."""
        return self._address

    @address.setter
    @sugartrail.api.auth
    def address(self, new_value):
        """address setter."""
        self._address = new_value
        self._ensure_network('Address', new_value)
        self.add_seed_node(new_value, 'Address', new_value)

    @property
    def addresses(self):
        if self._network_id is None:
            return []
        nodes = self._store.get_all_nodes_by_type(self._network_id, 'Address')
        address_table = []
        for node in nodes:
            arcs = self._store.get_arcs(self._network_id, node['node_id'])
            address = {
                "address": node['node_id'],
                "title": node['title'],
                "depth": node['depth'],
                'link_type': '',
                'link': ''
            }
            if not arcs:
                address_table.append(address)
            else:
                for arc in arcs:
                    entry = dict(address)
                    entry['link_type'] = arc['arc_type']
                    entry['link'] = arc['start_node']
                    address_table.append(entry)
        return address_table

    @property
    def file(self):
        """file property for loading pre-built network data into class."""
        return self._file

    @file.setter
    def file(self, new_value):
        """file setter for loading pre-built network data into class."""
        self._file = new_value
        self.load(self._file)

    def initialise_node(self, officer_id, company_id, address, file):
        """Builds initial network from arguments."""
        if self.n < 1:
            if officer_id:
                self.officer_id = officer_id
            elif company_id:
                self.company_id = company_id
            elif address:
                self.address = address
            elif file:
                self.file = file
            else:
                print("No input provided. Please provide either officer_id, company_id, address or file as input.")

    def save(self, filename, location='../assets/networks/'):
        """Saves network in JSON format to '../assets/networks/'."""
        data = self._store.export_network_json(self._network_id)
        if data:
            saved_network = json.dumps(data)
            filepath = location + f'{sugartrail.utils.ensure_json_extension(filename)}'
            with open(filepath, 'w') as f:
                f.write(saved_network)

    def load(self, filename):
        """Loads network stored in JSON format."""
        if filename:
            with open(filename) as f:
                data = json.load(f)
            self._network_id = self._store.import_network_json(data)
            self._officer_id = data.get('_officer_id')
            self._company_id = data.get('_company_id')
            self._address = data.get('_address')
            self.n = data.get('n', 0)
            self.hop_history = data.get('hop_history', [])
            self._node_cache = set(self._store.get_all_node_ids(self._network_id))

    def run_map_preprocessing(self):
        """Gets missing/additional information on companies and addresses required for
        mapping them. This includes address histories, company records and coordinates."""
        self.get_network_edge_address_histories()
        self.get_company_records_from_id()
        self.get_coords()
        return

    def get_company_records_from_id(self, company_df=None, print_progress=True):
        """Gets company records for all company IDs in the network."""
        company_list = self._store.get_nodes_at_depth(self._network_id, self.n, 'Company')
        all_companies = self._store.get_all_nodes_by_type(self._network_id, 'Company')
        company_list = [n['node_id'] for n in all_companies]
        for i, company_id in enumerate(company_list):
            if print_progress:
                print("Processed " + str(i+1) + "/" + str(len(company_list)) + " companies.")
            if self._store.get_company_record(company_id) is not None:
                continue
            if company_df is not None:
                try:
                    company = company_df[company_df[" CompanyNumber"] == str(company_id)]["CompanyName"].item()
                    if company:
                        self._store.upsert_company_record(company_id, company)
                except:
                    try:
                        company = sugartrail.api.get_company(company_id)
                        if company:
                            self._store.upsert_company_record(company_id, company)
                    except:
                        print(f"Failed to get data for {company_id}")
            else:
                company = sugartrail.api.get_company(company_id)
                if company:
                    self._store.upsert_company_record(company_id, company)
        self._store.commit()

    def get_network_edge_address_histories(self):
        """Gets missing address histories for companies at the edge of the network."""
        if self.hop.get_company_address_history:
            network_edge_companies = self._store.get_nodes_at_depth(self._network_id, self.n, 'Company')
            for i, company in enumerate(network_edge_companies):
                print("Processed " + str(i+1) + "/" + str(len(network_edge_companies)) + " company addresses.")
                address_history = sugartrail.processing.build_address_history(company)
                if address_history:
                    for address_entry in address_history:
                        if 'address' in address_entry:
                            self.add_address_history_entry(address_entry)
                            new_address = address_entry['address']
                            self._store.ensure_node(new_address, 'Address', new_address)
                            self._store.ensure_network_node(self._network_id, new_address, self.n + 1)
                            depth = self._store.get_node_depth(self._network_id, new_address)
                            if depth == self.n + 1:
                                self._store.add_edge(self._network_id, new_address, company, "Historic Address")
            self._store.commit()

    def get_coords(self):
        """Gets coordinates for each address in address_history."""
        history = self.address_history
        address_coords = {}
        for i, entry in enumerate(history):
            print("Processed " + str(i+1) + "/" + str(len(history)) + " addresses.")
            addr = entry['address']
            if addr not in address_coords:
                coords = sugartrail.utils.get_coords_from_address(addr)
                if coords:
                    address_coords[addr] = {'lat': coords['lat'], 'lon': coords['lon']}
                else:
                    address_coords[addr] = {'lat': None, 'lon': None}
            lat = address_coords[addr]['lat']
            lon = address_coords[addr]['lon']
            if lat is not None and lon is not None:
                self._store.update_address_history_coords(entry['company_number'], addr, lat, lon)
                self._store.update_node_coords(addr, lat, lon)
        self._store.commit()

    def find_path(self, company_id):
        """Finds path from 'select_company' to origin company'."""
        graph = self.graph
        path = []
        end_node = dict(graph[company_id])
        if not end_node['arcs']:
            end_node.update({
                'id': company_id,
                'link_type': '',
                'link': ''
                })
            path.append(dict((k, end_node[k]) for k in ('title', 'depth', 'node_type', 'id', 'link', 'link_type')))
        else:
            for arc in end_node['arcs']:
                connection = dict((k, end_node[k]) for k in ('title', 'depth', 'node_type'))
                connection.update({
                    'id': company_id,
                    'link_type': arc['arc_type'],
                    'link': arc['start_node']
                    })
                path.append(connection)
            for connection in path:
                id = connection['link']
                node = dict(graph[id])
                if node['arcs']:
                    for arc in node['arcs']:
                        connection = dict((k, node[k]) for k in ('title', 'depth', 'node_type'))
                        connection.update({
                            'id': id,
                            'link_type': arc['arc_type'],
                            'link': arc['start_node']
                            })
                        if connection not in path:
                            path.append(connection)
                else:
                    start_node = dict((k, node[k]) for k in ('title', 'depth', 'node_type'))
                    start_node.update({
                        'id': id,
                        'link_type': '',
                        'link': ''
                        })
                    path.append(start_node)
                    break
        path.reverse()
        path = sugartrail.processing.condense_path(path)
        path = sugartrail.processing.asciiify_path(path)
        return path

    def _copy_expanded_connections(self, source_id):
        """Re-use connections from a previous expansion of source_id."""
        edges = self._store.get_edges_from_source_any_network(source_id)
        for edge in edges:
            node_info = self._store.get_global_node(edge['end_node_id'])
            if node_info:
                self.add_node(
                    edge['end_node_id'], node_info['node_type'],
                    node_info['title'], source_id, edge['arc_type']
                )
        for entry in self._store.get_address_history_for_company(source_id):
            self.add_address_history_entry(entry)
        for m in self._store.get_maxsize_for_node_any_network(source_id):
            self.add_maxsize_entity(source_id, m['entity_type'], m['maxsize_type'], m['size'])

    def perform_hop(self, hops, company_data=None, print_progress=True):
        """Gets companies, officers and addresses within n-degrees of seperation
        from current nodes, where n is the number of hops."""
        hop_history = []
        for hop in range(hops):
            self.progress.intro_print = "Hop number: " + str(hop+1)
            self._node_cache = set(self._store.get_all_node_ids(self._network_id))
            self.progress.selected_addresses = self._store.get_nodes_at_depth(self._network_id, self.n, 'Address')
            self.progress.selected_officers = self._store.get_nodes_at_depth(self._network_id, self.n, 'Person')
            self.progress.selected_companies = self._store.get_nodes_at_depth(self._network_id, self.n, 'Company')
            if not self.progress.selected_addresses and not self.progress.selected_companies and not self.progress.selected_officers:
                print("Edge of network reached.")
                return
            else:
                self._store.commit()
                for i, address in enumerate(self.progress.selected_addresses):
                    self.progress.address_index = i
                    if address not in self.progress.processed_addresses:
                        if self._store.is_node_expanded(address):
                            self._copy_expanded_connections(address)
                        else:
                            self.hop.search_address(self, address, company_data)
                            self._store.mark_node_expanded(address)
                        self.progress.processed_addresses.append(address)
                    if print_progress:
                        self.progress.print_progress()
                for j, company in enumerate(self.progress.selected_companies):
                    self.progress.company_index = j
                    if company not in self.progress.processed_companies:
                        if self._store.is_node_expanded(company):
                            self._copy_expanded_connections(company)
                        else:
                            self.hop.search_company_id(self, company)
                            self._store.mark_node_expanded(company)
                        self.progress.processed_companies.append(company)
                    if print_progress:
                        self.progress.print_progress()
                for k, officer in enumerate(self.progress.selected_officers):
                    self.progress.officer_index = k
                    if officer not in self.progress.processed_officers:
                        if self._store.is_node_expanded(officer):
                            self._copy_expanded_connections(officer)
                        else:
                            self.hop.search_officer_id(self, officer)
                            self._store.mark_node_expanded(officer)
                        self.progress.processed_officers.append(officer)
                    if print_progress:
                        self.progress.print_progress()
                self.progress.processed_officers, self.progress.processed_companies, self.progress.processed_addresses = [], [], []
                self.progress.selected_officers, self.progress.selected_companies, self.progress.selected_addresses = [], [], []
                self.n += 1
                self._store.set_network_depth(self._network_id, self.n)
                hop_history.append(self.hop.__dict__)
                self._store.save_hop(self._network_id, self.n, self.hop.__dict__)
                self._store.commit()
            self.hop_history.extend(hop_history)
