# -*- coding: utf-8 -*-

import logging
from fhirclient import client
from fhirclient.models.medication import Medication
from fhirclient.models.medicationrequest import MedicationRequest
from fhirclient.models.claim import Claim
from fhirclient.models.encounter import Encounter

from flask import Flask, render_template, json, request, redirect, jsonify, url_for, session

# app setup
#'scope': 'launch/patient fhirUser openid patient/*.read user/*.read'
smart_defaults = {
    'app_id': 'HMpLixwYJvGntZhNPXdIgMJVrXeGA7qg',
    'app_secret': 'Q2PW1IT1buvHG5a7',
    'api_base': 'https://gcp-hcls-test.apigee.net/v1/r4/carin/',
    'redirect_uri': 'http://localhost:8000/fhir-app/',
    'scope': 'launch/patient fhirUser openid patient/*.read'
}

patient_config = {
    'Mrs. Katina266 Hamill307': '5b72debb-60d1-49f9-8f3a-8220f894ca95',
    'Ms. Joey457 Ritchie586':   '22efb1f8-3d1f-4cc6-9dfc-60aabcbe114c',
    'Mrs. Margery365 Kunde533': 'a28340a7-41e5-47ef-b0c9-e984341fa101',
}

app = Flask(__name__)

def _save_state(state):
    session['state'] = state

def _get_smart():
    state = session.get('state')
    if state:
        return client.FHIRClient(state=state, save_func=_save_state)
    else:
        return client.FHIRClient(settings=smart_defaults, save_func=_save_state)

def _logout():
    if 'state' in session:
        smart = _get_smart()
        smart.reset_patient()

def _reset():
    if 'state' in session:
        del session['state']

def _get_prescriptions(smart):
    bundle = MedicationRequest.where({'patient': smart.patient_id}).perform(smart.server)
    pres = [be.resource for be in bundle.entry] if bundle is not None and bundle.entry is not None else None
    if pres is not None and len(pres) > 0:
        return pres
    return None

def _get_claims(smart):
    bundle = Claim.where({'patient': smart.patient_id}).perform(smart.server)
    pres = [be.resource for be in bundle.entry] if bundle is not None and bundle.entry is not None else None
    if pres is not None and len(pres) > 0:
        return pres
    return None

def _get_medication_by_ref(ref, smart):
    #med_id = ref.split("/")[1]
    #med_id = ref.split("#")[1]
    #return Medication.read(med_id, smart.server).code
    med = ref.resolved(Medication)
    return med.code

def _med_name(med):
    if med.coding:
        #name = next((coding.display for coding in med.coding if coding.system == 'http://www.nlm.nih.gov/research/umls/rxnorm'), None)
        name = next((coding.display for coding in med.coding if coding.system == 'http://snomed.info/sct'), None)
        if name:
            return name
    if med.text and med.text:
        return med.text
    return "Unnamed Medication(TM)"

def _get_med_name(prescription, client=None):
    if prescription.medicationCodeableConcept is not None:
        med = prescription.medicationCodeableConcept
        return _med_name(med)
    elif prescription.medicationReference is not None and client is not None:
        #med = _get_medication_by_ref(prescription.medicationReference.reference, client)
        med = _get_medication_by_ref(prescription.medicationReference, client)
        return _med_name(med)
    else:
        return 'Error: medication not found'

def _get_claim_name(claim, client=None):
    if claim.procedure is not None:
        med = claim.procedure
        return med
    #elif claim.medicationReference is not None and client is not None:
    #    med = _get_medication_by_ref(claim.medicationReference, client)
    #    return _med_name(med)
    else:
        return 'Error: medication not found'


@app.route('/', methods=["GET","POST"])
def index():
    
    username = ''
    name = ''
    smart = _get_smart()
    user_authenticated = False
    body = ''
    
    if smart.ready and smart.patient is not None:       # "ready" may be true but the access token may have expired, making smart.patient = None
        
        user_authenticated = True
        
        name = smart.human_name(smart.patient.name[0] if smart.patient.name and len(smart.patient.name) > 0 else 'Unknown')
        
        if request.method == 'GET':
            username = name
        elif request.method == 'POST':
            username = request.form['username']
        
        patient_id = patient_config[username]
        
        print('[ INFO ] Smart Patient_ID:         {}'.format(smart.patient_id))
        print('[ INFO ] Entered patient_id:       {}'.format(patient_id))
        
        ##############################################
        # CLAIMS
        ##############################################
        claims = []
        if smart.patient_id == patient_id:
            #claim_bundle = Claim.where({'patient': smart.patient_id}).perform(smart.server)
            #print('[ INFO ] Claim JSON before: {}'.format(claim_bundle))
            claim_bundle = Claim.where({}).perform(smart.server)
            claim_json   = claim_bundle.as_json()['entry'][0]['resource']['item']
            #print('[ INFO ] Claim JSON after:  {}'.format(claim_bundle))
            
            #print('[ *********** ] Claim: {}'.format(claim_bundle.as_json()['entry'][0]))
            for claim in claim_json:
                try:
                    claim_value = claim['net']['value']
                    claim_desc  = claim['productOrService']['text']
                    claims.append({'claim_desc':claim_desc, 'claim_value':claim_value})
                    #print('[ *********** ] Claim: {} (${})'.format(claim_desc,claim_value))
                except Exception as e:
                    print('[ EXCEPTION ] {}'.format(e))
        
        ##############################################
        # Encounters
        ##############################################
        encounters = []
        if smart.patient_id == patient_id:
            #encounter_bundle = Encounter.where({'patient': smart.patient_id}).perform(smart.server)
            encounter_bundle = Encounter.where({'patient': patient_id}).perform(smart.server)
            encounter_json = encounter_bundle.as_json()['entry']
            #print('[ INFO ] Encounter JSON after:  {}'.format(encounter_json))
            #print('[ *********** ] Encounters: {}'.format(encounter_json))
            for encounter in encounter_json:
                try:
                    serviceProvider = encounter['resource']['serviceProvider']['display']
                    practitioner    = encounter['resource']['participant'][0]['individual']['display']
                    encounter_date  = encounter['resource']['period']['start']
                    encounter_desc  = encounter['resource']['type'][0]['text']
                    encounters.append({'provider':serviceProvider, 'practitioner':practitioner, 'encounter_date':encounter_date, 'encounter_desc':encounter_desc})
                except Exception as e:
                    print('[ EXCEPTION ] {}'.format(e))
    
    else:
        claims = ''
        encounters = ''
        auth_url = smart.authorize_url
        if auth_url is not None:
            body += """<center><p>Please <a href="{0}">authorize</a>.</p></center>""".format(auth_url)
        else:
            body += """<center><p>Running against a no-auth server, nothing to demo here.</p></center> """
        body += """<center><p><a href="/reset" style="font-size:small;">Reset</a></p></center>"""
    
    return render_template('index.html', user=name, username=username, body=body, user_authenticated=user_authenticated, claims=claims, encounters=encounters)




@app.route('/fhir-app/')
def callback():
    """ OAuth2 callback interception.
    """
    smart = _get_smart()
    try:
        smart.handle_callback(request.url)
    except Exception as e:
        return """<h1>Authorization Error</h1><p>{0}</p><p><a href="/">Start over</a></p>""".format(e)
    return redirect('/')


@app.route('/logout')
def logout():
    _logout()
    return redirect('/')


@app.route('/reset')
def reset():
    _reset()
    return redirect('/')


# start the app
if '__main__' == __name__:
    import flaskbeaker
    flaskbeaker.FlaskBeaker.setup_app(app)
    
    logging.basicConfig(level=logging.DEBUG)
    app.run(debug=True, port=8000)
