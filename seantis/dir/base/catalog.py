from five import grok

from itertools import groupby
from Products.CMFCore.utils import getToolByName

from zope.ramcache.ram import RAMCache

from seantis.dir.base.interfaces import (
    IDirectoryItemBase, 
    IDirectoryBase,
    IDirectoryCatalog
)
from seantis.dir.base import utils

directory_cache = RAMCache()
directory_cache.update(maxAge=0, maxEntries=10)

item_cache = RAMCache()
item_cache.update(maxAge=0, maxEntries=10000)

uncached = object()

def directory_cachekey(directory):
    return ''.join(map(str,(
        directory.id, 
        directory.modified(), 
        directory.child_modified
    )))

def directory_item_cachekey(directory, item):
    return directory_cachekey(directory) + str(item.getRID())

def get_object(directory, result):

    cachekey = directory_item_cachekey(directory, result)

    obj = item_cache.query(cachekey, default=uncached)
    
    if obj is uncached:
        obj = result.getObject()
        item_cache.set(obj, cachekey)
    
    return obj

class DirectoryCatalog(grok.Adapter):

    grok.context(IDirectoryBase)
    grok.provides(IDirectoryCatalog)

    def __init__(self, context):
        self.directory = context
        self.catalog = getToolByName(context, 'portal_catalog')
        self.path = '/'.join(context.getPhysicalPath())

    def sortkey(self):
        """Returns the default sortkey."""
        uca_sortkey = utils.unicode_collate_sortkey()
        return lambda i: uca_sortkey(i.title)

    def query(self, **kwargs):
        results = self.catalog(path={'query': self.path, 'depth': 1},
            object_provides=IDirectoryItemBase.__identifier__,
            **kwargs
        )
        return results

    def get_object(self, result):
        return get_object(self.directory, result)

    def items(self):
        cachekey = directory_cachekey(self.directory)
        result = directory_cache.query(cachekey, default=uncached)

        if result is uncached:
            result = map(self.get_object, self.query())
            directory_cache.set(result, cachekey)

        return result

    def filter(self, term):

        results = self.query(categories={'query':term.values(), 'operator':'and'})

        def filter_key(item):
            for category, value in term.items():
                if value == '!empty':
                    continue
                if not value in getattr(item, category):
                    return False
            return True

        return filter(filter_key, map(self.get_object, results))

    def search(self, text):
        return map(self.get_object, self.query(SearchableText=text))

    def possible_values(self, items, categories=None):
        """Returns a dictionary with the keys being the categories of the directory,
        filled with a list of all possible values for each category. If an item 
        contains a list of values (as opposed to a single string) those values 
        flattened. In other words, there is no hierarchy in the resulting list.

        """
        categories = categories or self.directory.all_categories()
        values = dict([(cat,list()) for cat in categories])
        
        for item in items:
            for cat in values.keys():
                for word in item.keywords(categories=(cat,)):
                    word and values[cat].append(word)

        return values

    def grouped_possible_values(self, items, categories=None):
        """Same as possible_values, but with the categories of the dictionary being
        unique and each value being wrapped in a tuple with the first element
        as the actual value and the second element as the count non-unique values.

        It's really the grouped result of possible_values.

        """

        possible = self.possible_values(items, categories)
        grouped = dict([(k, dict()) for k in possible.keys()])

        for category, items in possible.items():
            groups = groupby(sorted(items))
            for group, values in groups:
                grouped[category][group] = len(list(values))

        return grouped

    def grouped_possible_values_counted(self, items, categories=None):
        """Returns a dictionary of categories with a list of possible values
        including counts in brackets.

        """
        possible = self.grouped_possible_values(items, categories)
        result = dict((k, []) for k in possible.keys())

        for category, values in possible.items():
            counted = []
            for text, count in values.items():
                counted.append(utils.add_count(text, count))
            
            result[category] = sorted(counted, key=utils.unicode_collate_sortkey())

        return result

def children(folder, portal_type):
    """Returns the descendants of a folder that match the given portal type."""
    
    catalog = getToolByName(folder, 'portal_catalog')
    path = '/'.join(folder.getPhysicalPath())
    
    results = catalog(
        path={'query': path, 'depth':1}, 
        portal_type=portal_type
    )

    return [r.getObject() for r in results]