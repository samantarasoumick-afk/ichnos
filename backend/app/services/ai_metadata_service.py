def generate_dataset_summary(dataset):

    column_names = []

    pii_columns = 0

    sensitive_columns = 0

    for column in dataset.columns:

        column_names.append(column.name)

        classification = (
            column.classification or ""
        ).upper()

        if classification == "PII":
            pii_columns += 1

        elif classification == "SENSITIVE":
            sensitive_columns += 1

    summary = (
        f"{dataset.schema_name}.{dataset.name} "
        f"contains {len(dataset.columns)} columns. "
    )

    if pii_columns > 0:

        summary += (
            f"It includes {pii_columns} PII columns. "
        )

    if sensitive_columns > 0:

        summary += (
            f"It includes {sensitive_columns} "
            f"sensitive columns. "
        )

    if dataset.owner:

        summary += (
            f"Owned by {dataset.owner}. "
        )

    if dataset.domain:

        summary += (
            f"Domain: {dataset.domain}. "
        )

    return summary.strip()