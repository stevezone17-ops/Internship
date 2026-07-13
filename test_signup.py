import requests
import json
import random

session = requests.Session()
res_get = session.get('http://127.0.0.1:5000/signup')
csrf = ''
for line in res_get.text.split('\n'):
    if 'name="_csrf_token"' in line:
        csrf = line.split('value="')[1].split('"')[0]
        break

email = f'test{random.randint(1,10000)}@example.com'
print('Registering', email)
res_post = session.post('http://127.0.0.1:5000/api/signup', json={
    'name': 'Test User',
    'email': email,
    'password': 'Password1!',
    'confirm_password': 'Password1!',
    'pin': '1234',
    '_csrf_token': csrf
}, headers={'X-CSRFToken': csrf})
print('STATUS:', res_post.status_code)
print('JSON:', res_post.text)
