import requests
import re
import json
import sys
import os
import pprint
import copy

class Trello:
  object_types = [
    'boards',
    'cards',
    'lists',
    'labels',
    'plugins'
  ]
  
  def __init__(self, **kwargs):
    self.token = 'example_token'
    self.key = 'example_key'
    self.query = None
    self.base_url = 'https://trello.com/1/' 
    self.url = None
    self.data = {}
    self.query_params = None
    try:
      self.id = kwargs['id']
    except KeyError:
      self.id = None
    
  def getToken(self, scope='read'):
    url = 'https://trello.com/1/authorize'
    params = {
      'callback_method': 'fragment',
      'return_url': 'https://trello.com',
      'scope': scope,
      'expiration': '1day',
      'key': self.key,
      'name': 'biobanking-data',
    }
    token_req = requests.get(url, params = params)
    pprint.pprint(token_req)
    pprint.pprint(token_req.text)

  def get(self, object_id = None, **kwargs):
    if object_id is None:
      if self.id is not None:
        object_id = self.id
      else:
        raise TypeError('Trello::get object_id must not be none or self.id must be set')
    self.buildParams()
    url = '{base_url}/{object_id}'.format(base_url=self.base_url, object_id=object_id)
    req = requests.get(url, params=self.query_params)
    if req.status_code == 200:
      data = json.loads(req.text)
      self.data.update(data)
      self.id = self.data['id']
      self.url = url 
    else:
      raise Exception('Error, unable to retrieve data, status code {status_code}'.format(status_code=req.status_code))
    return self.data

  def buildParams(self, **kwargs):
    #build a set of parameters using kwargs and standard_params (e.g. token)
    #standard params defined here temporarily but should be passed as arg eventually
    standard_params = {
      'token': self.token,
      'key': self.key,
    }
    if self.query_params is None:
      self.query_params = standard_params.copy()
    else:
      self.query_params.update(standard_params)
    self.query_params.update(kwargs)

    return self.query_params

class Board(Trello):
  def __init__(self, **kwargs):
    super(Board, self).__init__(**kwargs)
    self.base_url += 'boards/'

  def getCards(self, board_id = None, **kwargs):
    params = self.buildParams(filter='all')
    if self.url is None:
      self.get(board_id)
    url = '{url}/cards/'.format(url=self.url)
    req = requests.get(url, params=params)
    cards = json.loads(req.text)
    self.data['cards'] = []
    for card_data in cards:
      card = Card(id=card_data['id'])
      #card.data = card_data
      card.get()
      self.data['cards'].append(card)
    return self.data['cards']

  def getPluginData(self, board_id, **kwargs):
    params = self.buildParams()
    if self.url is None:
      self.get(board_id)
    url = '{url}/pluginData'.format(url=self.url)
    req = requests.get(url, params=params)
    self.data['pluginData'] = json.loads(req.text)
    for plugin in self.data['pluginData']:
      if 'value' in plugin.keys():
        if isinstance(plugin['value'], str):
          plugin['value'] = json.loads(plugin['value'])
    return self.data['pluginData']

class Card(Trello):
  def __init__(self, **kwargs):
    super(Card, self).__init__(**kwargs)
    self.base_url += 'cards/'

  def get(self, **kwargs):
    self.buildParams(pluginData='true', actions='all')
    super(Card, self).get(**kwargs)

  def joinPluginData(self, plugin_data = {}, **kwargs):
    if len(plugin_data.keys()) == 0:
      board = Board(id=self.data['idBoard'])
      board.get()
      plugin_data = board.getPluginData(board.id)
    
    try:
      for card_plugin in self.data['pluginData']:
        #go through all the plugin data for this card and find which plugin it is
        for plugin in plugin_data:
          if plugin['idPlugin'] == card_plugin['idPlugin']:
            #for debugging, set the dataModel for this plugin
            #comment out if debug not required
            card_plugin['dataModel'] = plugin
            break

        #now use card_plugin['dataModel'] to process the values set to decoded data
        if isinstance(card_plugin['value'], str):
          card_plugin['value'] = json.loads(card_plugin['value'])
        mapped_data = {}
        if 'fields' in card_plugin['value'].keys():
          for field_id, field_val in card_plugin['value']['fields'].items():
            for plug_field in plugin['value']['fields']:
              if plug_field['id'] == field_id:
                for val in plug_field['o']:
                  if val['id'] == field_val:
                    mapped_data[plug_field['n']] = val['value']
        card_plugin['data'] = copy.deepcopy(mapped_data)
    except KeyError as ke:
      if str(ke) == 'pluginData':
        pass

    return self

class Checklist(Trello):
  def __init__(self, **kwargs):
    super(Checklist,self).__init__(**kwargs)
    self.base_url += 'checklists/'

  def get(self, **kwargs):
    self.buildParams()
    super(Checklist, self).get(**kwargs)
    



