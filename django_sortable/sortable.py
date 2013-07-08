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
  LIST_VALUES = 4
  DATETIME_SIMPLE = 5

# TODO: Document usage, write helper
class SortableWithHeaders(Sortable):

  def __init__(self, objects, fields=None, header_type=HeaderType.NONE, one_header='All', sorted_relations=None, related_header_field=None, listed=None):
    super(SortableWithHeaders, self).__init__(objects, fields)

    self.header_type = header_type
    self.sorted_relations = None
    self.listed = listed
    
    self.one_header = one_header

    self.sorted_relations = sorted_relations
    self.related_header_field = related_header_field

  def get_sorted_headers(self, direction='asc'):
    if self.header_type == HeaderType.NONE:
      res = list()
      res.append(self.header_one)
      return res
    elif self.header_type == HeaderType.ALPHA:
      import string

      if direction == 'desc':
        # reverse the string
        return string.ascii_uppercase[::-1]

      return string.ascii_uppercase
    elif self.header_type == HeaderType.M2M or self.header_type == HeaderType.FK:
      res = SortedDict()

      qs = self.sorted_relations
      if direction == 'desc':
        qs = qs.reverse()

      for item in qs:
        header = getattr(item, self.related_header_field)
        res[header] = item

      return res
    elif self.header_type == HeaderType.DATETIME_SIMPLE:
        res = SortedDict()
        # res['Today'] = 
        return ('Today', 'Last 7 days', 'Last 30 days', 'This year', 'More than 1 year ago')
    elif self.header_type == HeaderType.LIST_VALUES:
      return self.listed
      if direction == 'desc':
        return self.listed[::-1]
      else:
        return self.listed
    else:
      return self.one_header

  def sorted(self, field_name, direction='asc'):
    """Returns sorted dictionary of lists."""
    sorted_dict = SortedDict()

    sorted_items = super(SortableWithHeaders, self).sorted(field_name, direction)
    if self.header_type == HeaderType.NONE:
      sorted_dict[self.one_header] = sorted_items
      return sorted_dict

    sorted_headers = self.get_sorted_headers(direction)


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
    # elif self.header_type == HeaderType.DATETIME_SIMPLE:
    #   pass
        # sorted_dict = 



        # sorted_dict()

        # 1: (_('Today'), lambda qs, name: qs.filter(**{
        #     '%s__year' % name: now().year,
        #     '%s__month' % name: now().month,
        #     '%s__day' % name: now().day
        # })),
        # 2: (_('Past 7 days'), lambda qs, name: qs.filter(**{
        #     '%s__gte' % name: _truncate(now() - timedelta(days=7)),
        #     '%s__lt' % name: _truncate(now() + timedelta(days=1)),
        # })),
        # 3: (_('This month'), lambda qs, name: qs.filter(**{
        #     '%s__year' % name: now().year,
        #     '%s__month' % name: now().month
        # })),
        # 4: (_('This year'), lambda qs, name: qs.filter(**{
        #     '%s__year' % name: now().year,
        # })),
    elif self.header_type == HeaderType.LIST_VALUES:
      for value in sorted_headers: 
        filter_kwargs = {field_name: value}
        with_this_value = sorted_items.filter(**filter_kwargs)

        if with_this_value.count():
          sorted_dict[value] = with_this_value

    return sorted_dict
