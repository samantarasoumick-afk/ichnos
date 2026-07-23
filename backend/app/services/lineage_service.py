from collections import defaultdict


class LineageService:

    @staticmethod
    def downstream(dataset_id, lineage):

        graph = defaultdict(list)

        for edge in lineage:
            graph[str(edge.upstream_dataset_id)].append(edge)

        visited = set()
        result = []

        def dfs(node):

            for edge in graph[node]:

                child = str(edge.downstream_dataset_id)

                if child not in visited:
                    visited.add(child)
                    result.append(edge)
                    dfs(child)

        dfs(str(dataset_id))

        return result

    @staticmethod
    def upstream(dataset_id, lineage):

        reverse = defaultdict(list)

        for edge in lineage:
            reverse[str(edge.downstream_dataset_id)].append(edge)

        visited = set()
        result = []

        def dfs(node):

            for edge in reverse[node]:

                parent = str(edge.upstream_dataset_id)

                if parent not in visited:
                    visited.add(parent)
                    result.append(edge)
                    dfs(parent)

        dfs(str(dataset_id))

        return result