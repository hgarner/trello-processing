import re
import sys
import os
import jsonpath_rw as jsonp
import json
from pprint import pprint
from collections import OrderedDict
import configparser
import argparse
import requests
from datetime import datetime
import csv
from copy import deepcopy
from pprint import pprint

def import_json(filepath):
  cache_file = open(filepath, 'r')
  data = json.load(cache_file, object_pairs_hook=OrderedDict)
  cache_file.close()
  return data

# parse the path as json
# return list of matches (DatumInContext objects)
def get_path(target_data, path):
  json_path = jsonp.parse(path)
  # create a list of matches
  matches = [match for match in json_path.find(target_data)]
  # return the list of matches 
  # (DatumInContext objects, key properties: value, context (another DatumInContext object))
  # when we assign the value it must be in the jsonpath_rw match
  # object.context.value.[final part of path] (DatumInContext.context.value.[pathfield])
  return matches

# get a dict of all list_ids: {list}
def get_lists(data):
  list_path = '$.lists.[*]'

  list_matches = get_path(data, list_path)

  # populate lists with list id and list object
  lists = OrderedDict() 

  for board_list in list_matches:
    list_id = board_list.value['id']
    lists[list_id] = board_list.value

  return lists

# get a dict of all cards_ids: {card}
def get_cards(data):
  # get cards
  card_path = '$.cards.[*]'

  card_matches = get_path(data, card_path)

  # populate cards with card id and card object
  cards = OrderedDict() 

  for card in card_matches:
    card_id = card.value['id']
    cards[card_id] = card.value

  return cards

# get a dict of all card_ids: [checklist_ids]
def get_card_lists(cards):
  # populate cards with card id and list of checklist ids
  card_lists = OrderedDict()

  for card_id, card in cards.items():
    card_list_matches = get_path(card, '$.idChecklists.[*]')
    this_card_lists = [c.value for c in card_list_matches]
    card_lists[card_id] = this_card_lists

  return card_lists

# get a dict of all checklist_ids: {checklist}
def get_checklists(data):
  # get checklists
  checklists = OrderedDict()

  checklist_path = '$.checklists.[*]'

  checklist_matches = get_path(data, checklist_path)

  for checklist in checklist_matches:
    checklist_id = checklist.value['id']
    checklists[checklist_id] = checklist.value

  return checklists

# process card lists to match with checklist objects containing
# items with completed dates
def process_card_lists(data):
  lists = get_lists(data)
  cards = get_cards(data)
  card_lists = get_card_lists(cards)
  checklists = get_checklists(data)
  
  # go through all the checklists and pull out any entries that have completed dates or that have a 'Y' or 'N' and have state as complete
  checkitem_path = '$.checkItems.[*]'
  for check_id, checklist in checklists.items():
    checkitems = get_path(checklist, checkitem_path)
    dated_checkitems = []
    datematch_string = r'^(?P<item_prefix>\({0,1}[A-Za-z0-9\s]{1,}\){0,1}){0,1}\s{0,1}"(?P<item_text>.*?)":[\s"]*(?P<item_date>([0-9]{4}/[0-9]{2}/[0-9]{2})|(Y{4}/M{2}/D{2}))["]*$'
    confirmed_checkitems = []
    for checkitem in checkitems:
      # check if item is ticked (state is 'complete')
      if checkitem.value['state'] == 'complete':
        completed_date = re.search(datematch_string, checkitem.value['name'])
        # check if item matches date type - if so add with date
        # if not, just add as a 'Y'
        if completed_date is not None:
          if completed_date.group('item_date') is not None:
            item_text = ''
            #if completed_date.group('item_prefix') is not None:
            #  item_text += completed_date.group('item_prefix')
            item_text += completed_date.group('item_text')
            dated_checkitems.append({
              #'id': checkitem.value['id'], 
              'text': item_text, 
              'date': completed_date.group('item_date')
            })
        else:
          confirmed_checkitems.append({
            #'id': checkitem.value['id'], 
            'text': checkitem.value['name'], 
            'confirmed': 'Y' # confirmed.group(2)
          })

    checklists[check_id] = dated_checkitems + confirmed_checkitems

  # get the checklist object and replace the id in the cards dict with these lists
  for card_id, checklist_ids in card_lists.items():
    card_checklists = []
    for checklist_id in checklist_ids:
      try:
        card_checklists.append(checklists[checklist_id])
      except KeyError:
        pass

    card_lists[card_id] = card_checklists

  readable_card_lists = OrderedDict()

  # put cards in lists
  for card_id, card_list in card_lists.items():
    try:
      readable_card_lists[lists[cards[card_id]['idList']]['name']][cards[card_id]['name']] = card_list
    except KeyError:
      readable_card_lists[lists[cards[card_id]['idList']]['name']] = OrderedDict({
        cards[card_id]['name']: card_list,
      })

  return readable_card_lists

# convert the json data of lists/cards/checklists into a flat structure
# @param OrderedDict json data of {[list]: { [card]: {checklist, checklist}}}
# @param bool by_list if True, separate data by list name 
#        when getting all checklist item text, otherwise combine
# @return list flattened json as ['card_name', 'item_name', 'item_data']
def convert_json_to_flat(data, by_list = False):
  flat_data = []
  pprint(data)
  # set up a list to hold checklist item texts
  checklist_items = []
  for list_name, list_data in data.items():
    # for each list
    # first, get a list of every (unique) checklist item text
    # then go through each checklist and add items to row
    # in order of above list
    for card_name, card_data in list_data.items():
      for checklist in card_data:
        for item in checklist:
          if item['text'] not in checklist_items:
            checklist_items.append(item['text'])
  sorted_checklist_items = sorted(checklist_items)

  pprint(sorted_checklist_items)
  #assert False

  # now go through all the lists and add a row for each card
  # each row will contain an entry for all the sorted checklist items
  # either by list if by_list is True, or all checklist items otherwise
  for list_name, list_data in data.items():
    current_row = []
    current_row.append(list_name)

    # now go through each card/checklist
    # add all the sorted_checklist_items and data (date/confirmed)
    # if present
    for card_name, card_data in list_data.items():
      # start with the card name
      current_row.append(card_name)
      # if it's got no checklists, just add the row 
      if len(card_data) == 0:
        flat_data.append(current_row)

      # now add each item from sorted_checklist_items (all unique
      # checklist item texts) to an ordered dict as keys, then add data 
      # from relevant checklist items for this card
      row_checklist_items = OrderedDict.fromkeys(sorted_checklist_items)

      for checklist in card_data:
        for item in checklist:
          row_checklist_items[item['text']] = ''
          try:
            row_checklist_items[item['text']] = item['date']
          except KeyError:
            row_checklist_items[item['text']] = item['confirmed']
      

      for item, value in row_checklist_items.items():
        current_row.append(item)
        current_row.append(value)
      flat_data.append(current_row)
      # reset current row back before the start of this set of checklist items
      # i.e. this card
      current_row = current_row[:-(len(row_checklist_items)*2)]
      # reset current row back before the start of this card
      # i.e. this list
      current_row = current_row[:-1]
    # reset current row back to before this list
    current_row = current_row[:-1]

  return flat_data

def load_config(config_filename = 'trello_config.ini', config = None):
  root_dir = os.getcwd()
  if config is None:
    config = configparser.ConfigParser()
  config.read(os.path.join(root_dir, config_filename))
  pprint(config.sections())
  return config

def get_trello_dump(key, token, board_id):
  url = 'https://api.trello.com/1/boards/{board_id}?key={key}&token={token}&actions=all&cards=all&labels=all&lists=all&checklists=all&pluginData=true'

  trello_data = requests.get(url.format(key = key, token = token, board_id = board_id))

  if trello_data.status_code == 200:
    return trello_data.json()
  else:
    raise ValueError('get_trello_dump: returned status code not 200')

if __name__ == "__main__":
  global config 
  print(os.getcwd())
  parser = argparse.ArgumentParser(description='Process Trello export json files to return list/board names and checklist items with completed dates')
  parser.add_argument('--config', dest='config_filename', action='store', help='.ini configuration filename')
  global args
  args = parser.parse_args()
  config = load_config('trello_config.ini')
  pprint(config.sections())
  pprint(args.config_filename)
  #config = load_config(args.config_filename, config)

  print(config['boards']['board_keys'])
  board_keys = config['boards']['board_keys'].split(',')

  for board in board_keys:
    try:
      data = get_trello_dump(
        key = config['trello_keys']['key'],
        token = config['trello_keys']['token'],
        board_id = board
      )

      # dump the data to a file
      now = datetime.now()
      datestamp = '{now.day:0>2}{now.month:0>2}{now.year}.{now.hour:0>2}{now.minute:0>2}{now.second:0>2}'.format(now = now) 

      output_dir = os.path.join(config['files']['output_dir'], data['id'])

      if not os.path.exists(output_dir):
        os.mkdir(os.path.join(config['files']['output_dir'], data['id']))

      with open(os.path.join(output_dir, 'trello_{board_name}.{date}.json').format(board_name = re.sub('[\s\.\/]', '_', data['name']), date = datestamp), 'w') as dump_file:
        json.dump(data, dump_file, indent=2)
      
      # now process the board dump to get lists/cards/checklists with dates complete
      processed = process_card_lists(data)

      # dump json output
      with open(os.path.join(output_dir, 'trello_{board_name}.checklists.{date}.json').format(board_name = re.sub('[\s\.\/]', '_', data['name']), date = datestamp), 'w') as dump_file:
        json.dump(processed, dump_file, indent=2)

      # dump flatfile output
      processed_flat = convert_json_to_flat(processed)

      with open(os.path.join(output_dir, 'trello_{board_name}.checklists.{date}.csv').format(board_name = re.sub('[\s\.\/]', '_', data['name']), date = datestamp), 'w') as dump_file:
        writer = csv.writer(dump_file)
        for line in processed_flat:
          writer.writerow(line)

      # print success for board
      print('Success: board {board_id} successfully processed'.format(board_id = data['id']))

    except Exception as e:
    #  print('Error: unable to retrieve data for board id {board_id}'.format(board_id = board))
    #  pprint(e) 
      raise e
