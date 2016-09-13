import copy
import sys
import os
import json
import logging
import decimal
import datetime

import datapackage
from jsontableschema.exceptions import InvalidCastError
from jsontableschema.model import SchemaModel


def processor():
    return "%-32s" % os.path.basename(sys.argv[0]).split('.')[0].title()

logging.basicConfig(level=logging.DEBUG,
                    format="%(levelname)-8s:"+processor()+":%(message)s")


class CommonJSONEncoder(json.JSONEncoder):
    """
    Common JSON Encoder
    json.dumps(myString, cls=CommonJSONEncoder)
    """

    def default(self, obj):     # pylint: disable=method-hidden

        if isinstance(obj, decimal.Decimal):
            return {'type{decimal}': str(obj)}
        elif isinstance(obj, datetime.date):
            return {'type{date}': str(obj)}


class CommonJSONDecoder(json.JSONDecoder):
    """
    Common JSON Encoder
    json.loads(myString, cls=CommonJSONEncoder)
    """

    @classmethod
    def object_hook(cls, obj):  # pylint: disable=method-hidden
        if 'type{decimal}' in obj:
            try:
                return decimal.Decimal(obj['type{decimal}'])
            except decimal.InvalidOperation:
                pass
        if 'type{date}' in obj:
            try:
                return datetime.datetime \
                    .strptime(obj["type{date}"], '%Y-%m-%d') \
                    .date()
            except ValueError:
                pass

        return obj

    def __init__(self, **kwargs):
        kwargs['object_hook'] = self.object_hook
        super(CommonJSONDecoder, self).__init__(**kwargs)


# pylint: disable=too-few-public-methods
class ResourceIterator(object):

    def __init__(self, spec, copy, validate=False):
        self.spec = spec
        self.table_schema = SchemaModel(copy['schema'])
        self.validate = validate

    def __iter__(self):
        return self

    def __next__(self): # pylint: disable=no-self-use
        line = sys.stdin.readline().strip()
        if line == '':
            raise StopIteration()
        # logging.error('INGESTING: {}'.format(line))
        line = json.loads(line, cls=CommonJSONDecoder)
        if self.validate:
            for k, v in line.items():
                try:
                    self.table_schema.cast(k, v)
                except InvalidCastError:
                    logging.error('Bad value %r for field %s', v, k)
                    raise
        return line

    def next(self):
        return self.__next__()


def ingest():
    params = None
    first = True
    validate = False
    if len(sys.argv) > 3:
        first = sys.argv[1] == '0'
        params = json.loads(sys.argv[2])
        validate = sys.argv[3] == 'True'

    if first:
        return params, None, None

    dp_json = sys.stdin.readline().strip()
    if dp_json == '':
        logging.error('Missing input')
        sys.exit(1)
    dp = json.loads(dp_json)
    resources = dp.get('resources', [])
    original_resources = copy.deepcopy(resources)

    profiles = list(dp.get('profiles', {}).keys())
    profile = 'tabular'
    if 'tabular' in profiles:
        profiles.remove('tabular')
    if len(profiles)>0:
        profile = profiles.pop(0)
    schema = datapackage.schema.Schema(profile)
    schema.validate(dp)

    _ = sys.stdin.readline().strip()

    def resources_iterator(_resources, _original_resources):
        # we pass a resource instance that may be changed by the processing code,
        # so we must keep a copy of the original resource (used to validate incoming data)
        for resource, copy in zip(_resources, _original_resources):
            if 'path' not in resource:
                continue

            res_iter = ResourceIterator(resource, copy, validate)
            yield res_iter

    return params, dp, resources_iterator(resources, original_resources)


def spew(dp, resources_iterator):
    row_count = 0
    print(json.dumps(dp, ensure_ascii=True))
    for res in resources_iterator:
        print()
        for rec in res:
            line = json.dumps(rec, cls=CommonJSONEncoder, ensure_ascii=True)
            print(line)
            # logging.error('SPEWING: {}'.format(line))
            row_count += 1

    logging.info('Processed %d rows', row_count)