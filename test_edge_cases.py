import requests
import json

url = 'http://localhost:8000/chat'
user_id = 'test_edge_cases_1234'

results = {}

r1 = requests.post(url, json={'user_id': user_id, 'message': 'I want to do usg, where to go?'})
results['USG'] = r1.json()

r2 = requests.post(url, json={'user_id': user_id, 'message': 'I want to see patent, where to go?'})
results['Typo'] = r2.json()

r3 = requests.post(url, json={'user_id': user_id, 'message': 'I need urgent blood, where to go?'})
results['Urgency'] = r3.json()

r4 = requests.post(url, json={'user_id': user_id, 'message': 'guide me how to go there. I am at the ground floor parking.'})
results['Context'] = r4.json()

with open('test_results.json', 'w') as f:
    json.dump(results, f, indent=4)
print("Results saved to test_results.json")
