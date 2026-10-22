"""Central confirmation per message; network and credential failures retain ciphertext."""
import httpx


def synchronize(queue, routes, client):
    rows = queue.pending()
    if not rows:
        return 0
    try:
        route = routes[rows[0]['route']]
        response = client.post('/api/v1/ingestao/lote', json={'mensagens': [row['message'] for row in rows]},
                               headers={'Authorization': 'Bearer ' + route['token']})
        response.raise_for_status()
        results = response.json()['resultados']
        indices = [item['indice'] for item in results]
        if sorted(indices) != list(range(len(rows))):
            raise ValueError('Incomplete or repeated batch indices')
        for item in results:
            row = rows[item['indice']]
            if item['status'] in ('aceita', 'duplicada') and item.get('id_mensagem') == row['id']:
                queue.confirmed(row)
            elif item['status'] == 'rejeitada':
                status = item.get('http_status', 500)
                queue.failed(row, 'central_' + str(status), permanent=status in (400, 409, 422))
            else:
                queue.failed(row, 'invalid_confirmation')
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        for row in rows:
            queue.failed(row, type(exc).__name__)
    return len(rows)
