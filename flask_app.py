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


@app.route('/')
def index():
    """ The app's main page.
    """
    name = ''
    smart = _get_smart()
    #body = '<h1>SMART on FHIR WebApp</h1>'
    body = ''
    body += '<center><p><a href="/logout">Change patient</a></p></center>'
    
    if smart.ready and smart.patient is not None:       # "ready" may be true but the access token may have expired, making smart.patient = None
        body += '<div class="row">'
        body += '<div class="col-md-2 col-xs-1 "></div>'
        body += '<div class="col-md-8 col-xs-1 ">'
        
        name = smart.human_name(smart.patient.name[0] if smart.patient.name and len(smart.patient.name) > 0 else 'Unknown')
        body += "<center><p>You are authorized as <b>{0}</b>.</p></center>".format(name)
        ##############################################
        # CLAIMS
        ##############################################
        claims = []
        claim_bundle = Claim.where({'patient': smart.patient_id}).perform(smart.server)
        claim_json = claim_bundle.as_json()['entry'][0]['resource']['item']
        #print('[ *********** ] Claim: {}'.format(claim_bundle.as_json()['entry'][0]))
        body += '<br><b>Claims:</b><br>'
        body += '<ul>'
        for claim in claim_json:
            try:
                claim_value = claim['net']['value']
                claim_desc  = claim['productOrService']['text']
                claims.append({'claim_desc':claim_desc, 'claim_value':claim_value})
                body += '<li>{} (${})</li>'.format(claim_desc,claim_value)
                #print('[ *********** ] Claim: {} (${})'.format(claim_desc,claim_value))
            except Exception as e:
                print('[ EXCEPTION ] {}'.format(e))
        
        body += '</ul>'
        
        ##############################################
        # Encounters
        ##############################################
        encounters = []
        encounter_bundle = Encounter.where({'patient': smart.patient_id}).perform(smart.server)
        encounter_json = encounter_bundle.as_json()['entry']
        body += '<br><b>Encounters:</b><br>'
        body += '<ul>'
        #print('[ *********** ] Encounters: {}'.format(encounter_json))
        for encounter in encounter_json:
            try:
                serviceProvider = encounter['resource']['serviceProvider']['display']
                practitioner    = encounter['resource']['participant'][0]['individual']['display']
                encounter_date  = encounter['resource']['period']['start']
                encounter_desc  = encounter['resource']['type'][0]['text']
                encounters.append({'provider':serviceProvider, 'practitioner':practitioner, 'encounter_date':encounter_date, 'encounter_desc':encounter_desc})
                body += '<li>{}:&nbsp;&nbsp;{}&nbsp;&nbsp;({})&nbsp; - &nbsp;{}</li>'.format(encounter_date,serviceProvider,practitioner,encounter_desc)
            except Exception as e:
                print('[ EXCEPTION ] {}'.format(e))
        
        body += '</ul>'
        
        ##############################################
        # Prescriptions
        ##############################################
        '''
        body += "<p>You are logged in as <b>{0}</b>.</p>".format(name)
        body += '<br><p><a href="/logout">Change patient</a></p>'
        pres = _get_prescriptions(smart)
        if pres is not None:
            body += "<p>{0} prescriptions: <ul><li>{1}</li></ul></p>".format("His" if 'male' == smart.patient.gender else "Her", '</li><li>'.join([_get_med_name(p,smart) for p in pres]))
        else:
            body += "<p>(There are no prescriptions for {0})</p>".format("him" if 'male' == smart.patient.gender else "her")
        '''
        
        body += '</div>'
        body += '<div class="col-md-8 col-xs-1 "></div>'
        body += '</div>'
    
    else:
        auth_url = smart.authorize_url
        if auth_url is not None:
            body += """<center><p>Please <a href="{0}">authorize</a>.</p></center>""".format(auth_url)
        else:
            body += """<center><p>Running against a no-auth server, nothing to demo here.</p></center> """
        body += """<center><p><a href="/reset" style="font-size:small;">Reset</a></p></center>"""
    
    return render_template('index.html', user=name, body=body)




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
