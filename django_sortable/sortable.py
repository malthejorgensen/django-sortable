from operator import itemgetter, attrgetter
from django.utils.datastructures import SortedDict

#TODO 
# sniff the field_name to decide how to sort if not explicitly told

class SortableInvalidObjectsException(Exception): pass


class Sortable(object):
  """docstring for Sortable"""
  
  def __init__(self, objects, fields):
    super(Sortable, self).__init__()
    self.objects = objects
    self.fields = None
    self.set_normalized_fields(fields)
  
  
  def set_normalized_fields(self, fields):
    """Takes name-to-field mapping tuple, normalizes it, and sets field."""
    if fields is None:
      return
    
    field_list = []
    for f in fields:
      if isinstance(f, basestring):
        field_list.append((f, (f,)))
      elif isinstance(f[1], basestring):
        field_list.append((f[0], (f[1],)))
      else:
        field_list.append(f)
    self.fields = dict(field_list)
  
    
  def sorted(self, field_name, direction='asc'):
    """Returns QuerySet with order_by applied or sorted list of dictionary."""
    
    if self.fields:
      try:
        fields = self.fields[field_name]
      except KeyError:
        return self.objects
    else:
      fields = (field_name,)
    
    if direction not in ('asc', 'desc'):
      return self.objects
    
    fields = Sortable.prepare_fields(fields, direction)
    
    if hasattr(self.objects, 'order_by'):
      result = self.objects.order_by(*fields)
    elif isinstance(self.objects, (list, tuple)):
      if len(self.objects) < 2:
        return self.objects
      
      comparers = []
      getter = itemgetter if isinstance(self.objects[0], dict) else attrgetter
      for f in fields:
        field = f[1:] if f.startswith('-') else f
        comparers.append((getter(field), 1 if field == f else -1))

      def comparer(left, right):
        for func, polarity in comparers:
          result = cmp(func(left), func(right))
          return 0 if not result else polarity * result
      
      result = sorted(self.objects, cmp=comparer)
    else:
      raise SortableInvalidObjectsException('An object of this type can not be sorted.')
    
    return result
  
  
  def sql_predicate(self, field_name, direction='asc', default=None):
    """Returns a predicate for use in a SQL ORDER BY clause."""
    
    if self.fields:
      try:
        fields = self.fields[field_name]
      except KeyError:
        fields = default
    else:
      fields = field_name
    
    if direction not in ('asc', 'desc'):
      fields = default
    
    fields = Sortable.prepare_fields(fields, direction, sql_predicate=True)
    return ', '.join(fields)


  @staticmethod
  def prepare_fields(fields, direction, sql_predicate=False):
    """Given a list or tuple of fields and direction, return a list of fields 
    with their appropriate order_by direction applied.

    >>> fields = ['++one', '--two', '+three', 'four', '-five']
    >>> Sortable.prepare_fields(fields, 'asc')
    ['one', '-two', 'three', 'four', '-five']
    >>> Sortable.prepare_fields(fields, 'desc')
    ['one', '-two', '-three', '-four', 'five']
    >>> Sortable.prepare_fields(fields, 'not_asc_or_desc')
    ['one', '-two', 'three', 'four', '-five']
    >>> Sortable.prepare_fields(fields, 'desc', True)
    ['one ASC', 'two DESC', 'three DESC', 'four DESC', 'five ASC']
    """
    
    if direction not in ('asc', 'desc'):
      direction = 'asc'  
    
    fields = list(fields)
    for i, field in enumerate(fields):
      if field.startswith('--'):
        fields[i] = field[1:]
      elif field.startswith('++'):
        fields[i] = field[2:]
      elif field.startswith('-'):
        fields[i] = (direction == 'asc' and '-' or '') + field[1:]
      else:
        field = field[1:] if field.startswith('+') else field
        fields[i] = (direction == 'desc' and '-' or '') + field
        
    if not sql_predicate:
      return fields
    
    # determine sql predicates from list
    fields = list(fields)
    for i, field in enumerate(fields):
      if field.startswith('-'):
        fields[i] = '%s DESC' % (field[1:],)
      else:
        fields[i] = '%s ASC' % (field,)
    return fields

# TODO: Do can FK/M2M be combined? Add RAGE_DATE and RANGE_NUM
class HeaderType(object):
  NONE = 0
  ALPHA = 1
  M2M = 2
  FK = 3

# TODO: Document usage, write helper
class SortableWithHeaders(Sortable):

  def __init__(self, objects, fields, header_type=HeaderType.NONE, one_header='All', sorted_relations=None, related_header_field=None):
    super(SortableWithHeaders, self).__init__(objects, fields)

    self.header_type = header_type
    self.sorted_relations = None
    
    if header_type == HeaderType.NONE:
      self.one_header = None
    else:
      self.one_header = one_header

    self.sorted_relations = sorted_relations
    self.related_header_field = related_header_field

  def get_sorted_headers(self):
    if self.header_type == HeaderType.NONE:
      return list(self.one_header,)
    elif self.header_type == HeaderType.ALPHA:
      import string
      return string.ascii_uppercase
    elif self.header_type == HeaderType.M2M or self.header_type == HeaderType.FK:
      res = SortedDict()
      for item in self.sorted_relations:
        header = getattr(item, self.related_header_field)
        res[header] = item

      return res
    else:
      return self.one_header

  def sorted(self, field_name, direction='asc'):
    """Returns sorted dictionary of lists."""
    sorted_dict = SortedDict()

    sorted_items = super(SortableWithHeaders, self).sorted(field_name, direction)
    sorted_headers = self.get_sorted_headers()

    if len(sorted_headers) < 2:
      if self.one_header == None: # Just return the items
        return sorted_items
      else:
        sorted_dict[self.one_header] = sorted_items
        return sorted_dict

    # Sort depending on the type of sort
    if self.header_type == HeaderType.ALPHA:
      for letter in sorted_headers:
        filter_kwargs = { '{0}__istartswith'.format(field_name): letter}
        starts_with_this_letter = sorted_items.filter(**filter_kwargs)
        
        if starts_with_this_letter.count():
            sorted_dict[letter] = starts_with_this_letter
    elif self.header_type == HeaderType.M2M or self.header_type == HeaderType.FK:
      for header, obj in sorted_headers.iteritems():
        filter_kwargs = { field_name: obj }
        in_this_header = sorted_items.filter(**filter_kwargs)

        if in_this_header.count():
          sorted_dict[header] = in_this_header


    return sorted_dict
