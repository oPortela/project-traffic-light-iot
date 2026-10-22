"""Allowlisted sorting and parameterized text filtering shared by data listings."""
from fastapi import HTTPException


def listing(conn, *, source, projection, tenant_column, tenant, columns, sort, filter_value, page, size):
    column = columns.get(sort.lstrip('-'))
    if column is None:
        raise HTTPException(422, 'Ordenacao invalida')
    where = tenant_column + '=%s'
    params = [tenant]
    if filter_value:
        where += ' AND (' + ' OR '.join('position(lower(%s) in lower(' + col + '::text))>0'
                                      for col in dict.fromkeys(columns.values())) + ')'
        params.extend([filter_value] * len(set(columns.values())))
    query = ' FROM ' + source + ' WHERE ' + where
    total = conn.execute('SELECT count(*) AS n' + query, params).fetchone()['n']
    order = column + (' DESC' if sort.startswith('-') else ' ASC') + ',' + columns['id']
    items = conn.execute('SELECT ' + projection + query + ' ORDER BY ' + order + ' LIMIT %s OFFSET %s',
                         [*params, size, (page - 1) * size]).fetchall()
    return {'page': page, 'size': size, 'total': total, 'items': items}
