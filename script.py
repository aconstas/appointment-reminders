from compliments import compliments, get_random_compliment

import os
import re
import smtplib, ssl
import json

from dotenv import load_dotenv
load_dotenv()

import requests
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

options = Options()
options.add_argument("-headless")
options.binary_location = '/usr/bin/firefox-esr' # Path to Firefox binary on Pi

today = datetime.now()
tomorrow = today + timedelta(days=1)
tomorrow_weekday_abbrev = tomorrow.strftime("%a")
tomorrow_formatted = tomorrow_weekday_abbrev + ', ' + tomorrow.strftime("%m/%d/%Y")
current_year = today.strftime("%g")

sender_email = os.getenv('GAPP_EMAIL')
receiver_email = os.getenv('GAPP_EMAIL')
password = os.getenv('GAPP_PASSWORD') # Google App Password
site_url = os.getenv('SITE_URL')
site_username = os.getenv('USERNAME')
site_password = os.getenv('PASSWORD')



def getCatImageUrl():
    response = requests.get("https://api.thecatapi.com/v1/images/search")
    data = json.loads(response.text)
    return data[0].get("url")

def getRandomCompliment():
    return get_random_compliment()

def createClientTable(clients):
    table_html = """
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
        <tr style="background-color: #f2f2f2;">
            <th>Time</th>
            <th>Client</th>
            <th>Phone</th>
            <th>Gender</th>
            <th>Age</th>
        </tr>
    """
    for client in clients:
        table_html += f"""
        <tr>
            <td>{client['time']}</td>
            <td>{client['name']}</td>
            <td>{client['phone']}</td>
            <td>{client['gender']}</td>
            <td>{client['age']}</td>
        </tr>
        """
    table_html += "</table>"
    return table_html

def createEmailBody(clients, cat_image_url, random_compliment):
    client_table = createClientTable(clients)
    body = f"""
    <html>
    <body>
    <h2>Client Information</h2>
    {client_table}
    <br>
    <img src="{cat_image_url}" alt="Cat of the day" style="max-width: 100%; height: auto;">
    <br>
    <h1>{random_compliment}</h1>
    </body>
    </html>
    """
    return body


def constructEmail(sender_email, receiver_email, clients, cat_image_url, random_compliment):
    message = MIMEMultipart("alternative")
    message["Subject"] = f'{tomorrow_formatted} Clinic Details'
    message["From"] = sender_email
    message["To"] = receiver_email
    
    body = createEmailBody(clients, cat_image_url, random_compliment)
    message.attach(MIMEText(body, 'html'))
    
    return message

def sendEmail(sender_email, password, receiver_email, message):
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender_email, password)
        server.sendmail(
            sender_email, receiver_email, message.as_string()
        )

# Log into site
service = Service('/usr/local/bin/geckodriver')
driver = webdriver.Firefox(service=service, options=options)
driver.get(site_url)
user = driver.find_element(By.NAME, "____login_login")
user.send_keys(site_username)
pwd = driver.find_element(By.NAME, "____login_password")
pwd.send_keys(site_password)
pwd.send_keys(Keys.RETURN)

clients = []

try:
    element = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.LINK_TEXT, 'Appointments'))
    )
    element.click()

    tomorrows_clinic = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.LINK_TEXT, tomorrow_formatted))
    )
    tomorrows_clinic.click()

    appointments_table = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CLASS_NAME, 'tablelistview'))
    )
    tbody = appointments_table.find_element(By.TAG_NAME, 'tbody')
    rows = tbody.find_elements(By.TAG_NAME, 'tr')

    for row in rows:
        if row.text and current_year in row.text:
            columns = row.find_elements(By.TAG_NAME, 'td')
            time = columns[0].text
            name_link = columns[1].find_element(By.TAG_NAME, 'a')
            name = name_link.text
            link_url = name_link.get_attribute('href')
            
            client = {
                "name": name,
                "time": time,
                "link": link_url
            }
            clients.append(client)

    print("Initial client information:")
    for client in clients:
        print(client)

    # Function to scrape additional details from each client's page
    def scrape_client_details(client):
        try:
            driver.get(client['link'])

            page_source = driver.page_source
            
            phone_pattern = r'\((\d{3})\)\s*(\d{3})-(\d{4})'
            phone_match = re.search(phone_pattern, page_source)
            
            if phone_match:
                client['phone'] = phone_match.group()
            else:
                client['phone'] = "Phone number not found"

        # get gender / age in tab at bottom of page
            try:
                client_demographics_tab = driver.find_element(By.LINK_TEXT, 'CLIENT DEMOGRAPHICS')
                client_demographics_tab.click()

                age_label = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Age')]"))
                )

                age_value = age_label.find_element(By.XPATH, "../following-sibling::td//span").text
                client['age'] = age_value
                
                gender_label = driver.find_element(By.XPATH, "//label//a[contains(text(), 'Gender')]")
                gender_value = gender_label.find_element(By.XPATH, "../../../td[@class='rrow form_value']//span").text
                client['gender'] = gender_value
            finally:
                pass

        except Exception as e:
            print(f"Error scraping details for {client['name']}: {str(e)}")
        
        return client

    # Scrape additional details for each client
    for client in clients:
        scrape_client_details(client)

except Exception as e:
    print(f"An error occurred: {str(e)}")

try:
    if clients:
        cat_image_url = getCatImageUrl()
        random_compliment = getRandomCompliment()
        email_message = constructEmail(sender_email, receiver_email, clients, cat_image_url, random_compliment)
        sendEmail(sender_email, password, receiver_email, email_message)
finally:
    driver.quit()
