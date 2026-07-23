def generate_dataset_description(
    dataset_name: str,
    schema_name: str,
    columns: list
):

    column_names = [
        column[0]
        for column in columns
    ]

    joined_columns = ", ".join(
        column_names[:8]
    )

    dataset_name_lower = (
        dataset_name.lower()
    )

    if "customer" in dataset_name_lower:

        return (
            "Contains customer-related "
            "records including "
            f"{joined_columns}."
        )

    if "payment" in dataset_name_lower:

        return (
            "Contains payment and "
            "financial transaction data "
            f"including {joined_columns}."
        )

    if "employee" in dataset_name_lower:

        return (
            "Contains employee and HR "
            "information including "
            f"{joined_columns}."
        )

    return (
        f"Dataset in schema "
        f"{schema_name} containing "
        f"{joined_columns}."
    )