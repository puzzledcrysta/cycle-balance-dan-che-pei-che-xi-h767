from dataclasses import dataclass
from decimal import Decimal as D
from app.errors import DataError
from .values import whole, number, parts


@dataclass
class Arc:
    destination: int
    reverse: int
    capacity: int
    cost: D


def connect(graph, a, b, quantity, cost):
    forward = Arc(b, len(graph[b]), quantity, cost)
    backward = Arc(a, len(graph[a]), 0, -cost)
    graph[a].append(forward)
    graph[b].append(backward)
    return forward


def augment(graph, source, sink):
    distances = {source:D(0)}
    previous = {}
    for _ in range(len(graph)-1):
        changed = False
        for node, edges in enumerate(graph):
            if node not in distances:
                continue
            for index, edge in enumerate(edges):
                cost = distances[node] + edge.cost
                if edge.capacity and (edge.destination not in distances or cost < distances[edge.destination]):
                    distances[edge.destination] = cost
                    previous[edge.destination] = (node,index)
                    changed = True
        if not changed:
            break
    if sink not in previous:
        return 0
    node, path = sink, []
    while node != source:
        parent, index = previous[node]
        edge = graph[parent][index]
        path.append(edge)
        node = parent
    moved = min(edge.capacity for edge in path)
    for edge in path:
        edge.capacity -= moved
        graph[edge.destination][edge.reverse].capacity += moved
    return moved


def evaluate(row):
    stations = {}
    for raw in parts(row['站点余缺']):
        name, sep, count = raw.partition(':')
        if not sep or not name or name in stations:
            raise DataError('CYCLE_STATION', f'站点名重复或缺失 {name}')
        stations[name] = whole(count,-50,50)
    if not 2 <= len(stations) <= 35:
        raise DataError('CYCLE_STATION', '站点数须在 2 至 35 之间')
    indices = {name:i for i,name in enumerate(sorted(stations))}
    source,sink = len(indices),len(indices)+1
    graph = [[] for _ in range(sink+1)]
    need = 0
    for name,i in indices.items():
        count = stations[name]
        if count > 0:
            connect(graph,source,i,count,D(0))
        elif count < 0:
            need -= count
            connect(graph,i,sink,-count,D(0))
    tracked = {}
    for item in sorted(parts(row['可行车路'])):
        pieces = item.split(':')
        if len(pieces) != 3:
            raise DataError('CYCLE_ROAD', '车路须包含方向、容量、距离')
        label, raw_count, raw_cost = pieces
        a, _, b = label.partition('>')
        if a not in indices or b not in indices or a == b or label in tracked:
            raise DataError('CYCLE_ROAD', f'车路重复或端点无效 {label}')
        capacity = whole(raw_count,1,1000)
        distance = number(raw_cost,D('0.001'),1000)
        tracked[label] = (capacity,connect(graph,indices[a],indices[b],capacity,distance))
    transported = 0
    while moved := augment(graph,source,sink):
        transported += moved
    total, proof = D(0), []
    for label,(capacity,edge) in tracked.items():
        flow = capacity-edge.capacity
        if flow:
            total += flow*edge.cost
            proof.append((label,flow,'辆'))
    proof.extend([('调配完成',transported,'辆'),('未满足',need-transported,'辆')])
    return total, proof
