import IPython
import os
import sugartrail

def find_network_connections(first_network, second_network, max_depth=5, print_progress=False):
    """Returns a list of nodes connecting ."""
    hops = 0
    while hops < max_depth:
        first_network.progress.pre_print = str(hops) + "/" + str(max_depth) + " hops completed."
        second_network.progress.pre_print = str(hops) + "/" + str(max_depth) + " hops completed."
        if first_network.n < hops:
            first_network.perform_hop(1, print_progress=print_progress)
        if second_network.n < hops:
            second_network.perform_hop(1, print_progress=print_progress)
        hops += 1

        if first_network._store is second_network._store:
            intersections = first_network._store.intersect_networks(
                first_network._network_id, second_network._network_id
            )
            connectors = [node_id for node_id, _ in intersections]
        else:
            first_keys = set(first_network.graph.keys())
            second_keys = set(second_network.graph.keys())
            connectors = [x for x in first_keys & second_keys if x]
        if connectors:
            print("Found connection(s)!")
            return connectors
        print(str(hops) + "/" + str(max_depth) + " hops completed.")
    print("No connections found.")
    return

def load_multiple_networks(networks_dir, store=None):
    """Loads multiple network files from a directory into a list"""
    entity_graphs = []
    for filename in os.listdir(networks_dir):
        if filename.endswith('.json'):
            kwargs = {}
            if store is not None:
                kwargs['store'] = store
            network = sugartrail.base.Network(file=f'{networks_dir}/{filename}', **kwargs)
            entity_graphs.append(network)
    return entity_graphs

def find_multi_network_connections(networks: list):
    """Finds the shortest paths connecting 2+ networks from a list of networks,
    returning nodes within these found paths."""
    s_path_network = []
    for i, entity in enumerate(networks):
        for j in range(i+1, len(networks)):
            if networks[i]._store is networks[j]._store:
                intersections = networks[i]._store.intersect_networks(
                    networks[i]._network_id, networks[j]._network_id
                )
                if not intersections:
                    continue
                min_depth = intersections[0][1]
                filtered_data = [node_id for node_id, depth_sum in intersections if depth_sum == min_depth]
            else:
                graph_i = networks[i].graph
                graph_j = networks[j].graph
                connections = [
                    (x, graph_i[x]['depth'] + graph_j[x]['depth'])
                    for x in filter(graph_i.__contains__, graph_j.keys()) if x
                ]
                sorted_data = sorted(connections, key=lambda x: x[1])
                filtered_data = [x[0] for x in filter(lambda x: x[1] == sorted_data[0][1], sorted_data)]
            for connection in filtered_data:
                for entity_graph in [networks[i], networks[j]]:
                    for node in entity_graph.find_path(connection):
                        network_node = {'title': node['title'],
                                         'node_type': node['node_type'],
                                         'id': node['id'],
                                         'link_type': node['link_type'],
                                         'link' : "",
                                         'depth': node['depth']
                                        }
                        if node['link']:
                            for link in [x.strip() for x in node['link'].split(',')]:
                                new_node = network_node.copy()
                                new_node['link'] = next((item['id'] for item in entity_graph.find_path(connection) if item["node_index"] == link), None)
                                if new_node not in s_path_network:
                                    s_path_network.append(new_node)
                        else:
                            new_node = network_node.copy()
                            s_path_network.append(new_node)
    return s_path_network
