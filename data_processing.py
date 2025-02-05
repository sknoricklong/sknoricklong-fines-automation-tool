import re
import requests
import time
from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd

def longest_streak(data):
    data['date'] = pd.to_datetime(data['date'])
    data.set_index('date', inplace=True)
    fee_table_monthly = data.resample('M').count().reset_index()
    max_streak = 0
    current_streak = 0
    total_paid_months = 0

    # Ensure the values in the data are numeric
    fee_table_monthly = fee_table_monthly.apply(pd.to_numeric, errors='coerce')

    for i, row in fee_table_monthly.iterrows():
        if row[1] > 0:
            total_paid_months += 1
            current_streak += 1

            if current_streak > max_streak:
                max_streak = current_streak
        else:
            current_streak = 0

    return max_streak


def update_amount_by_name(fee_table, first_name, last_name, case_number):
    full_name = f'{last_name.upper()}, {first_name.upper()}'
    name_rows = fee_table[(fee_table['amount'] == 0.0) & (fee_table['description'].str.contains(full_name))]

    for index, row in name_rows.iterrows():
        text = row['description']
        amounts = re.findall(
            r'' + re.escape(case_number) + r':\s*\$([\d,.]+)\s+ON TRANSFER TO.*?' + re.escape(full_name) + r'\b', text)
        if amounts:
            total_amount = sum([float(amount.replace(',', '')) for amount in amounts])
            fee_table.loc[index, 'amount'] = total_amount

    return fee_table

def extract_and_calculate(fee_table, first_name, last_name, case_number):
    fee_table = fee_table.drop_duplicates()

    # Remove rows with 'VICTIMS' in the description
    fee_table = fee_table[~fee_table['description'].str.contains('VICTIMS', case=False, na=False)]

    full_name = f'{last_name.upper()}, {first_name.upper()}'
    if fee_table['party'].isnull().all() or fee_table['party'].eq('').all():
        pass
    else:
        try:
            first_name = first_name.lower()
            last_name = last_name.lower()

            mask = ((fee_table['party'].str.lower().str.contains(first_name)) | \
                    (fee_table['party'].str.lower().str.contains(last_name)) | \
                    (fee_table['description'].str.lower().str.contains(first_name)) & \
                    (fee_table['description'].str.lower().str.contains(last_name))).fillna(False)

            fee_table = fee_table[mask]

        except AttributeError:
            pass

    # Add a new column "payment_plan" with 1 if "payment plan" is found in the 'description' column, 0 otherwise
    has_payment_plan = int(fee_table['description'].str.lower().str.contains('payment plan').any())
    already_received_waiver = int(fee_table['description'].str.lower().str.contains('grants 983a').any())

    # Your original code
    fee_table_issued1 = fee_table[fee_table["amount"].str.contains('\d', na=False)]

    # Fix the SettingWithCopyWarning
    fee_table_issued1 = fee_table_issued1.copy()
    fee_table_issued1.loc[:, 'amount'] = fee_table_issued1['amount'].str.replace('[ ,$]', '', regex=True).astype(float)

    if not (fee_table_issued1['amount'] > 0).any():
        # The alternative code
        fee_table_issued2 = fee_table.copy()
        fee_table_issued2['amount'] = fee_table['description'].str.extract(r'\[(?:.*?)(\d+\.\d{2})(?:.*?)\]')
        fee_table_issued2['amount'] = pd.to_numeric(fee_table_issued2['amount'], errors='coerce')

        fee_table_issued2 = fee_table_issued2[
            ~fee_table_issued2['code'].isin(['ACCOUNT', 'PAY', 'TEXT'])
        ]

        fee_table_issued2 = fee_table_issued2[~fee_table_issued2['code'].str.contains('AC')]

        # Concatenate both results
        fee_table_issued = pd.concat([fee_table_issued1, fee_table_issued2]).drop_duplicates().reset_index(drop=True)
    else:
        fee_table_issued = fee_table_issued1

    total_amount_owed = round(fee_table_issued['amount'].sum(), 2)

    fee_table = fee_table[
        fee_table['code'].isin(['ACCOUNT', 'PAY', 'TEXT'])
    ]

    fee_table_copy = fee_table.copy()

    # Extract the dollar amount from the description column using regular expressions
    pattern = r'TOTAL AMOUNT PAID:\s*\$?\s*(\d+\.\d{2})'
    fee_table['amount'] = fee_table['description'].str.extract(pattern)
    fee_table['amount'] = fee_table['amount'].str.replace('$', '', regex=True).astype(float)
    fee_table = fee_table.dropna(subset=['amount'])
    fee_table = fee_table[fee_table['amount'] >= 0]

    if len(fee_table) == 0:
        pattern = r'TOTAL AMOUNT PAID ON CASE # [A-Za-z0-9-]* : \$\s?(\d+\.\d{2})'
        fee_table = fee_table_copy.copy()
        fee_table['amount'] = fee_table['description'].str.extract(pattern)
        fee_table['amount'] = fee_table['amount'].str.replace('$', '', regex=True).astype(float)
        fee_table = fee_table[fee_table['description'].str.lower().str.contains('receipt', na=False)]

    fee_table.reset_index(drop=True, inplace=True)
    # Update the 'amount' column in fee_table for rows with a 0.0 amount and the full name in the 'description' column
    fee_table = update_amount_by_name(fee_table, first_name, last_name, case_number)
    fee_table_paid = fee_table.copy()
    total_amount_paid = fee_table['amount'].sum()
    fee_table['date'] = pd.to_datetime(fee_table['date'])

    fee_table.set_index('date', inplace=True)
    fee_table_monthly = fee_table.resample('M').count().reset_index()

    def longest_streak(data):
        max_streak = 0
        current_streak = 0
        end_month = None
        total_paid_months = 0

        for i, row in data.iterrows():
            if row[1] > 0:
                total_paid_months += 1
                current_streak += 1

                if current_streak > max_streak:
                    max_streak = current_streak
                    end_month_index = row['date']
                    end_month = fee_table.loc[fee_table.index <= end_month_index].index.max()
                    start_month_index = data.loc[i - max_streak + 1, 'date']
                    start_month = fee_table.loc[fee_table.index >= start_month_index].index.min()
            else:
                current_streak = 0

        return max_streak, total_paid_months, end_month

    streak_length, total_paid_months, streak_end = longest_streak(fee_table_monthly)


    return streak_length, total_paid_months, streak_end, total_amount_paid, total_amount_owed, has_payment_plan, already_received_waiver, fee_table_paid, fee_table_issued

def extract_fee_table(soup):
    tables = soup.select("table[id*='results-list']")  # Select tables with 'results-list' in the id
    dataframes = []
    for table in tables:
        try:
            df = pd.read_html(str(table))[0]

            # Extract links from the table
            rows = table.find_all('tr')
            links = []
            for row in rows[1:]:  # Skip the header row
                link_cell = row.find('a', href=True)
                if link_cell:
                    links.append(link_cell['href'])
                else:
                    links.append(None)

            # Add a new column to the DataFrame with the links
            df['Link'] = links

            dataframes.append(df)
        except:
            pass
    return dataframes

def extract_docket_table(soup):
    tables = soup.select("table.docketlist.ocis, table.docketlist.kp")
    dataframes = []
    for table in tables:
        try:
            df = pd.read_html(str(table))[0]
            dataframes.append(df)
        except:
            pass
    fee_table = pd.concat(dataframes)
    fee_table.columns = [col.lower() for col in fee_table.columns]
    fee_table['date'] = fee_table['date'].fillna(method='ffill')
    default_amount = ""
    fee_table['amount'].fillna(default_amount, inplace=True)

    return fee_table

@st.cache_data
def search_cases(guid, first_name, last_name, middle_name=''):
    base_url = "https://www.oscn.net/dockets/Results.aspx?db=all&number=&lname={}&fname={}&mname={}"

    # Format the URL with the provided names
    url = base_url.format(last_name, first_name, middle_name)
    progress_text = st.empty()
    # Define headers for the request
    headers = {
        "User-Agent": guid,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }

    # Make the request
    response = requests.get(url, headers=headers)
    # If the request was successful, parse the result
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')


        # Find all tr elements with class 'resultTableRow'
        rows = soup.find_all('tr', class_='resultTableRow')

        # Prepare empty lists for DataFrame
        case_numbers = []
        dates = []
        case_names = []
        found_names = []
        counties = []
        links = []
        htmls = []
        counter = 1
        case_number_set = set()  # Set to store case numbers

        # Loop through each row
        for row in rows:
            tds = row.find_all('td')
            case_number = tds[0].text.strip()

            if case_number in case_number_set:
                counter += 1
                continue  # Skip adding rows with duplicate case numbers

            case_number_set.add(case_number)
            case_numbers.append(case_number)
            dates.append(tds[1].text.strip())
            case_names.append(tds[2].text.strip())
            found_names.append(tds[3].text.strip())
            link = "https://www.oscn.net/dockets/" + tds[0].find('a')['href']
            links.append(link)
            response = requests.get(link, headers=headers)
            htmls.append(BeautifulSoup(response.content, 'html.parser'))
            time.sleep(1)

            # Find the county, strip everything after "Found", and convert to title case
            full_county_text = row.find_previous('table', class_='caseCourtTable').find('caption',
                                                                                        class_='caseCourtHeader').text.strip()
            county = full_county_text.split("Found")[0].strip().title()
            counties.append(county)
            progress_text.text(f'Finished {counter} of {len(rows)}: {tds[0].text.strip()}')
            counter += 1

        # Create DataFrame
        df = pd.DataFrame({
            'Case Number': case_numbers,
            'Court': counties,
            'Found Party': found_names,
            'Date': dates,
            'Case Name': case_names,
            'Link': links,
            'HTML': htmls

        })

        try:
            df['Court'] = df['Court'].replace(['Court', 'County'], '', regex=True).str.strip().str.title()
        except AttributeError:
            st.write(f"No results found for {first_name.title()} {last_name.title()}")

        return df

    else:
        print(f"Failed to get page, status code: {response.status_code}")
        return pd.DataFrame()  # Return empty DataFrame if request fails


@st.cache_data
def navigate_and_get_url_soups(url_list, case_list, guid):
    base_url = "https://www.oscn.net/dockets/Results.aspx?db=all&number=&lname={}&fname={}&mname={}"

    # Format the url with the provided names
    url = base_url.format("jordan", "leroy", "albert")

    # Define headers for the request
    headers = {
        "User-Agent": guid,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }

    # Make the request
    response = requests.get(url, headers=headers)
    # If the request was successful, parse the result
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        st.write(soup)


def create_case_soup_dict(case_list, html_list):
    oscn_case_soup_dict = {}
    for case, html in zip(case_list, html_list):
        oscn_case_soup_dict[case] = html
    return oscn_case_soup_dict


def process_urls(case_soup_dict, first_name, last_name):
    results = {}

    for case_number, html in case_soup_dict.items():
        soup = BeautifulSoup(html, 'html.parser')
        fee_table = extract_docket_table(soup)
        result = extract_and_calculate(fee_table, first_name, last_name, case_number)
        results[case_number] = result

    return results