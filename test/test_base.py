import sugartrail
import json
import tempfile
import os

# test 1: network initialised without auth and without arguments:

def test_init_without_arguments(capsys):
    sugartrail.base.Network()
    captured = capsys.readouterr()
    assert captured.out == 'No input provided. Please provide either officer_id, company_id, address or file as input.\n'

# test 2: network initialised without auth and with arguments prints auth requirement:

def test_init_officer_without_auth(capsys):
    sugartrail.base.Network(officer_id = '_')
    captured = capsys.readouterr()
    assert captured.out == 'Authentication required\n'

def test_init_company_without_auth(capsys):
    sugartrail.base.Network(company_id = '_')
    captured = capsys.readouterr()
    assert captured.out == 'Authentication required\n'

def test_init_address_without_auth(capsys):
    sugartrail.base.Network(address = '_')
    captured = capsys.readouterr()
    assert captured.out == 'Authentication required\n'

# test 3: network initialised without auth and with arguments remains stateless:

def test_empty_officer_without_auth(capsys):
    network = sugartrail.base.Network(officer_id = '_')
    assert network._officer_id == None

def test_empty_company_without_auth(capsys):
    network = sugartrail.base.Network(company_id = '_')
    assert network._company_id == None

def test_empty_address_without_auth(capsys):
    network = sugartrail.base.Network(address = '_')
    assert network._address == None

# test 4: network initialised with 'file' arg without auth loads network:

def test_file_init_without_auth():
    network = sugartrail.base.Network(file='./assets/networks/example_network.json')
    with open('./assets/networks/example_network.json') as f:
        network_json = json.load(f)
    assert network._officer_id == network_json.get('_officer_id')
    assert network._company_id == network_json.get('_company_id')
    assert network._address == network_json.get('_address')
    assert network.n == network_json['n']
    assert len(network.graph) == len(network_json['graph'])

# test 5: network loads network from file without auth:

def test_file_load_without_auth():
    network = sugartrail.base.Network()
    network.load('./assets/networks/example_network.json')
    with open('./assets/networks/example_network.json') as f:
        network_json = json.load(f)
    assert network._officer_id == network_json.get('_officer_id')
    assert network._company_id == network_json.get('_company_id')
    assert network._address == network_json.get('_address')
    assert network.n == network_json['n']
    assert len(network.graph) == len(network_json['graph'])

# test 6: JSON export round-trips correctly:

def test_export_roundtrip():
    network = sugartrail.base.Network(file='./assets/networks/example_network.json')
    with tempfile.TemporaryDirectory() as tmpdir:
        network.save('roundtrip_test', location=tmpdir + '/')
        with open(os.path.join(tmpdir, 'roundtrip_test.json')) as f:
            exported = json.load(f)
    with open('./assets/networks/example_network.json') as f:
        original = json.load(f)
    assert len(exported['graph']) == len(original['graph'])
    assert exported['_officer_id'] == original.get('_officer_id')
    assert exported['_company_id'] == original.get('_company_id')
    assert exported['n'] == original['n']

# test 7: GraphProxy supports dict-like access:

def test_graph_proxy_access():
    network = sugartrail.base.Network(file='./assets/networks/example_network.json')
    with open('./assets/networks/example_network.json') as f:
        original = json.load(f)
    first_key = list(original['graph'].keys())[0]
    assert first_key in network.graph
    node = network.graph[first_key]
    assert node['node_type'] == original['graph'][first_key]['node_type']
    assert node['depth'] == original['graph'][first_key]['depth']
    assert 'NONEXISTENT_KEY' not in network.graph
