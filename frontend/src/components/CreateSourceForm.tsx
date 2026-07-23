"use client";

import { useState } from "react";

import api from "../services/api";

const DEFAULT_PORTS: Record<string, string> = {
  postgres: "5432",
  mysql: "3306",
  redshift: "5439",
  azure_sql: "1433",
};

export default function CreateSourceForm() {

  const [name, setName] = useState("");

  const [type, setType] = useState("postgres");

  const [host, setHost] = useState("");

  const [port, setPort] = useState(DEFAULT_PORTS.postgres);

  const [database, setDatabase] = useState("");

  const [user, setUser] = useState("");

  const [password, setPassword] = useState("");

  // Snowflake-only fields - it identifies a source by account
  // (not host/port) and separates the compute warehouse from the
  // database; schema/role are optional.
  const [account, setAccount] = useState("");

  const [warehouse, setWarehouse] = useState("");

  const [schema, setSchema] = useState("");

  const [role, setRole] = useState("");

  // S3-only fields - object storage has no host/port/database/user
  // shape at all, so this is a distinct field set entirely rather
  // than another branch squeezed into the SQL-connector fields below.
  const [bucket, setBucket] = useState("");

  const [prefix, setPrefix] = useState("");

  const [region, setRegion] = useState("");

  const [accessKeyId, setAccessKeyId] = useState("");

  const [secretAccessKey, setSecretAccessKey] = useState("");

  const [loading, setLoading] = useState(false);

  const isSnowflake = type === "snowflake";
  const isS3 = type === "s3";

  function handleTypeChange(nextType: string) {
    setType(nextType);
    // Only swap the port if it's still sitting on the previous type's
    // default - don't clobber a value the user already typed in.
    if (Object.values(DEFAULT_PORTS).includes(port)) {
      setPort(DEFAULT_PORTS[nextType] ?? port);
    }
  }

  async function createSource() {

    try {

      setLoading(true);

      const connection_config = isSnowflake
        ? {
            account,
            warehouse,
            database,
            schema: schema || undefined,
            role: role || undefined,
            user,
            password,
          }
        : isS3
        ? {
            bucket,
            prefix: prefix || undefined,
            region: region || undefined,
            access_key_id: accessKeyId || undefined,
            secret_access_key: secretAccessKey || undefined,
          }
        : {
            host,
            port,
            database,
            user,
            password,
          };

      await api.post("/api/sources", {
        name,
        type,
        connection_config,
      });

      alert("Source created successfully");

      window.location.reload();

    } catch (error) {

      console.error(error);

      alert("Failed to create source");

    } finally {

      setLoading(false);
    }
  }

  return (

    <div>

      <div className="grid grid-cols-2 gap-4">

        <select
          value={type}
          onChange={(e) => handleTypeChange(e.target.value)}
          className="border p-3 rounded"
        >
          <option value="postgres">PostgreSQL</option>
          <option value="mysql">MySQL</option>
          <option value="snowflake">Snowflake</option>
          <option value="redshift">Amazon Redshift</option>
          <option value="s3">Amazon S3</option>
          <option value="azure_sql">Azure SQL Database / Synapse</option>
        </select>

        <input
          placeholder="Source Name"
          value={name}
          onChange={(e) =>
            setName(e.target.value)
          }
          className="border p-3 rounded"
        />

        {isS3 && (
          <>
            <input
              placeholder="Bucket"
              value={bucket}
              onChange={(e) => setBucket(e.target.value)}
              className="border p-3 rounded"
            />
            <input
              placeholder="Prefix (optional - e.g. exports/)"
              value={prefix}
              onChange={(e) => setPrefix(e.target.value)}
              className="border p-3 rounded"
            />
            <input
              placeholder="Region (optional)"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="border p-3 rounded"
            />
            <input
              placeholder="Access Key ID (optional - uses IAM role if blank)"
              value={accessKeyId}
              onChange={(e) => setAccessKeyId(e.target.value)}
              className="border p-3 rounded"
            />
            <input
              type="password"
              placeholder="Secret Access Key (optional)"
              value={secretAccessKey}
              onChange={(e) => setSecretAccessKey(e.target.value)}
              className="border p-3 rounded"
            />
          </>
        )}

        {!isS3 && (
          <>
            {isSnowflake ? (

              <input
                placeholder="Account (e.g. xy12345.us-east-1)"
                value={account}
                onChange={(e) =>
                  setAccount(e.target.value)
                }
                className="border p-3 rounded"
              />

            ) : (

              <input
                placeholder="Host"
                value={host}
                onChange={(e) =>
                  setHost(e.target.value)
                }
                className="border p-3 rounded"
              />

            )}

            {isSnowflake ? (

              <input
                placeholder="Warehouse"
                value={warehouse}
                onChange={(e) =>
                  setWarehouse(e.target.value)
                }
                className="border p-3 rounded"
              />

            ) : (

              <input
                placeholder="Port"
                value={port}
                onChange={(e) =>
                  setPort(e.target.value)
                }
                className="border p-3 rounded"
              />

            )}

            <input
              placeholder="Database"
              value={database}
              onChange={(e) =>
                setDatabase(e.target.value)
              }
              className="border p-3 rounded"
            />

            {isSnowflake && (

              <input
                placeholder="Schema (optional - all schemas if blank)"
                value={schema}
                onChange={(e) =>
                  setSchema(e.target.value)
                }
                className="border p-3 rounded"
              />

            )}

            {isSnowflake && (

              <input
                placeholder="Role (optional)"
                value={role}
                onChange={(e) =>
                  setRole(e.target.value)
                }
                className="border p-3 rounded"
              />

            )}

            <input
              placeholder="User"
              value={user}
              onChange={(e) =>
                setUser(e.target.value)
              }
              className="border p-3 rounded"
            />

            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) =>
                setPassword(e.target.value)
              }
              className="border p-3 rounded"
            />
          </>
        )}

      </div>

      <button
        onClick={createSource}
        disabled={loading}
        className="
          mt-6
          bg-black
          text-white
          px-6
          py-3
          rounded-xl
        "
      >
        {loading
          ? "Creating..."
          : "Create Source"}
      </button>

    </div>
  );
}
