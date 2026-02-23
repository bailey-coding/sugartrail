import sugartrail

class Hop:
    """Class attributes store the criteria for each hop. Class contains
    methods for getting officers, addresses and companies using the
    criteria."""
    def __init__(self):
        self.get_company_officers = True
        self.get_company_address_history = True
        self.get_psc_correspondance_address = True
        self.get_officer_appointments = True
        self.officer_appointments_maxsize = 50
        self.get_officer_correspondance_address = True
        self.get_officer_duplicates = True
        self.officer_duplicates_maxsize = None
        self.get_officers_at_address = True
        self.officers_at_address_maxsize = 50
        self.get_companies_at_address = True
        self.companies_at_address_maxsize = 50

    def search_company_id(self, network, company_id):
        """Gets officers and addresses connected to input company
        (company_id)."""
        officers = []
        if self.get_company_officers:
            officers = sugartrail.api.get_company_officers(company_id)
            if officers:
                if 'items' in officers:
                    officers = officers['items']
        if officers:
            for officer in officers:
                new_officer_id = str(officer['links']['officer']['appointments'].split('/')[2])
                if new_officer_id not in network._node_cache:
                    try:
                        title = sugartrail.api.get_appointments(new_officer_id)['items'][0]['name']
                    except:
                        print(f"failed to get title for officer: {new_officer_id}")
                        try:
                            title = sugartrail.utils.normalise_name(officer['name'])
                        except:
                            print(f"failed to get title for officer: {new_officer_id}")
                            title = new_officer_id
                else:
                    title = None
                network.add_node(new_officer_id, 'Person', title, company_id, 'Officer')
        if self.get_psc_correspondance_address:
        # get address for company pscs
            psc = sugartrail.api.get_psc(company_id)
            if psc:
                if 'items' in psc:
                    for person in psc['items']:
                        if "address" in person:
                            new_address = sugartrail.utils.normalise_address(person['address'])
                            network.add_node(new_address, 'Address', new_address, company_id, 'Person of Significant Control Address')
        if self.get_company_address_history:
        # get company address history
            address_history = sugartrail.processing.build_address_history(company_id)
            if address_history:
                for address in address_history:
                    if 'address' in address:
                        network.add_address_history_entry(address)
                        new_address = address['address']
                        network.add_node(new_address, 'Address', new_address, company_id, 'Historic Address')

    def search_officer_id(self, network, officer_id):
        """Gets officers, companies and addresses connected to input officer
        (officer_id)."""
        appointments = sugartrail.api.get_appointments(officer_id)
        if appointments:
            if self.officer_appointments_maxsize == None or len(appointments['items']) < int(self.officer_appointments_maxsize or 0):
                for appointment in appointments['items']:
                    new_company = appointment['appointed_to']['company_number']
                    network.add_node(new_company, 'Company', appointment['appointed_to']['company_name'], officer_id, 'Appointment')
            elif len(appointments['items']) > int(self.officer_appointments_maxsize):
                network.add_maxsize_entity(officer_id, 'Officer', 'Appointments', len(appointments['items']))
        if self.get_officer_correspondance_address:
            correspondance_address = sugartrail.api.get_correspondance_address(officer_id)
            if correspondance_address:
                new_address = sugartrail.utils.normalise_address(correspondance_address['items'][0]['address'])
                network.add_node(new_address, 'Address', new_address, officer_id, 'Officer Corresponance Address')
        if self.get_officer_duplicates:
            duplicate_officers = sugartrail.api.get_duplicate_officers(officer_id)
            if duplicate_officers:
                if self.officer_duplicates_maxsize == None or len(duplicate_officers) < int(self.officer_duplicates_maxsize or 0):
                    for duplicate in duplicate_officers:
                        new_officer = duplicate['links']['self'].split('/')[2]
                        network.add_node(new_officer, 'Person', duplicate['title'], officer_id, 'Duplicate Officer')
                elif len(duplicate_officers) > int(self.officer_duplicates_maxsize):
                    network.add_maxsize_entity(officer_id, 'Officer', 'Duplicates', len(duplicate_officers))

    def search_address(self, network, address, company_data):
        """Gets officers, companies and addresses connected to input officer
        (officer_id)."""
        if self.get_companies_at_address:
            companies = {}
            if company_data is not None:
                companies['items'] = sugartrail.processing.get_companies_from_address_database(address, company_data)
            else:
                companies = sugartrail.api.get_companies_at_address(address)
            if companies:
                if 'items' in companies:
                    if self.companies_at_address_maxsize == None or len(companies['items']) < int(self.companies_at_address_maxsize or 0):
                        for company in companies['items']:
                            new_company = company['company_number']
                            network.add_node(new_company, 'Company', company['company_name'], address, 'Company at Address')
                    elif len(companies['items']) > int(self.companies_at_address_maxsize):
                        network.add_maxsize_entity(address, 'Address', 'Companies', len(companies['items']))
        if self.get_officers_at_address:
            officers = sugartrail.api.get_officers_at_address(address)
            if officers:
                if self.officers_at_address_maxsize == None or len(officers) < int(self.officers_at_address_maxsize or 0):
                    for officer in officers:
                        if 'links' and 'title' in officer:
                            new_officer = officer['links']['self'].split('/')[2]
                            network.add_node(new_officer, 'Person', officer['title'], address, 'Officer at Address')
                elif len(officers) > int(self.officers_at_address_maxsize):
                    network.add_maxsize_entity(address, 'Address', 'Officers', len(officers))
