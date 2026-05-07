import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Database, List, Plus, Trash2 } from "lucide-react";
import { Button, Card, CardContent, Input } from "@/components/ui";
import { createExtractionSchema, ExtractionSchemaCreate, ExtractionSchemaOut, listExtractionSchemas, updateExtractionSchema } from "@/lib/docaiApi";
import { mockSchema } from "@/lib/mockData";

type SelectedMode = "field" | "table" | null;
type SchemaField = { id: string; name: string; type: string; required: boolean; description?: string };
type SchemaColumn = { id: string; name: string; type: string };
type SchemaTable = { id: string; name: string; description?: string; columns: SchemaColumn[] };
type SchemaDraft = { fields: SchemaField[]; tables: SchemaTable[] };

const cloneSchema = (schema: SchemaDraft): SchemaDraft => ({
  fields: schema.fields.map((f) => ({ ...f })),
  tables: schema.tables.map((t) => ({ ...t, columns: t.columns.map((c) => ({ ...c })) })),
});
const createInitialSchema = (): SchemaDraft => cloneSchema(mockSchema as SchemaDraft);
const uniqueName = (base: string, names: string[]) => {
  const used = new Set(names.map((n) => n.trim().toLowerCase()));
  if (!used.has(base.toLowerCase())) return base;
  let i = 1; while (used.has(`${base} ${i}`.toLowerCase())) i += 1; return `${base} ${i}`;
};
const nextId = (prefix: string, ids: string[]) => {
  const nums = ids.map((id) => (id.startsWith(prefix) ? Number(id.slice(prefix.length)) : NaN)).filter((n) => Number.isFinite(n)) as number[];
  return `${prefix}${nums.length ? Math.max(...nums) + 1 : 1}`;
};
const toDraft = (s: ExtractionSchemaOut): SchemaDraft => ({
  fields: (s.fields || []).map((f, i) => ({ id: f.id?.trim() || `f${i + 1}`, name: f.name || `Field ${i + 1}`, type: f.type || "string", required: Boolean(f.required), description: f.description || "" })),
  tables: (s.tables || []).map((t, i) => ({ id: t.id?.trim() || `t${i + 1}`, name: t.name || `Table ${i + 1}`, description: t.description || "", columns: (t.columns || []).map((c, j) => ({ id: c.id?.trim() || `c${j + 1}`, name: c.name || `Column ${j + 1}`, type: c.type || "string" })) })),
});
const toPayload = (name: string, documentType: string, d: SchemaDraft): ExtractionSchemaCreate => ({
  name: name.trim(),
  document_type: documentType.trim() || undefined,
  fields: d.fields.map((f) => ({ id: f.id, name: f.name, type: f.type, required: f.required, description: f.description || "" })),
  tables: d.tables.map((t) => ({ id: t.id, name: t.name, description: t.description || "", columns: t.columns.map((c) => ({ id: c.id, name: c.name, type: c.type })) })),
});

export default function SchemaBuilderPage() {
  const { id: projectId } = useParams();
  const initial = useMemo(() => createInitialSchema(), []);
  const [schemaId, setSchemaId] = useState<string | null>(null);
  const [schemaName, setSchemaName] = useState("Extraction Schema");
  const [documentType, setDocumentType] = useState("invoice");
  const [loadedSchemaName, setLoadedSchemaName] = useState("Extraction Schema");
  const [loadedDocumentType, setLoadedDocumentType] = useState("invoice");
  const [schemaDraft, setSchemaDraft] = useState<SchemaDraft>(() => cloneSchema(initial));
  const [loadedSnapshot, setLoadedSnapshot] = useState<SchemaDraft>(() => cloneSchema(initial));
  const [selectedMode, setSelectedMode] = useState<SelectedMode>(initial.fields.length ? "field" : initial.tables.length ? "table" : null);
  const [selectedFieldId, setSelectedFieldId] = useState<string | null>(initial.fields[0]?.id || null);
  const [selectedTableId, setSelectedTableId] = useState<string | null>(initial.fields.length ? null : initial.tables[0]?.id || null);
  const [statusNote, setStatusNote] = useState("Unsaved schema draft.");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const selectedField = schemaDraft.fields.find((f) => f.id === selectedFieldId) || null;
  const selectedTable = schemaDraft.tables.find((t) => t.id === selectedTableId) || null;
  const markUnsaved = () => setStatusNote("Unsaved schema draft.");
  const selectField = (id: string) => { setSelectedMode("field"); setSelectedFieldId(id); setSelectedTableId(null); };
  const selectTable = (id: string) => { setSelectedMode("table"); setSelectedTableId(id); setSelectedFieldId(null); };

  const applySnapshot = (nextSchemaId: string | null, nextName: string, nextDocType: string, nextDraft: SchemaDraft, note: string) => {
    const cloned = cloneSchema(nextDraft);
    setSchemaId(nextSchemaId); setSchemaName(nextName); setDocumentType(nextDocType);
    setLoadedSchemaName(nextName); setLoadedDocumentType(nextDocType);
    setSchemaDraft(cloned); setLoadedSnapshot(cloneSchema(cloned)); setStatusNote(note);
    if (cloned.fields.length) selectField(cloned.fields[0].id);
    else if (cloned.tables.length) selectTable(cloned.tables[0].id);
    else { setSelectedMode(null); setSelectedFieldId(null); setSelectedTableId(null); }
  };

  useEffect(() => {
    if (!projectId) { setError("Missing project id in route."); return; }
    setLoading(true); setError(null);
    void listExtractionSchemas(projectId).then((schemas) => {
      if (schemas.length) {
        const s = schemas[0];
        applySnapshot(s.schema_id, s.name, s.document_type || "", toDraft(s), "Loaded from backend.");
      } else {
        applySnapshot(null, "Extraction Schema", "invoice", cloneSchema(initial), "Unsaved schema draft.");
      }
    }).catch((e) => {
      setError(e instanceof Error ? e.message : "Failed to load schemas from backend.");
      applySnapshot(null, "Extraction Schema", "invoice", cloneSchema(initial), "Unsaved schema draft.");
    }).finally(() => setLoading(false));
  }, [projectId]);

  const addField = () => {
    const field = { id: nextId("f", schemaDraft.fields.map((f) => f.id)), name: uniqueName("New Field", schemaDraft.fields.map((f) => f.name)), type: "string", required: false, description: "" };
    setSchemaDraft((p) => ({ ...p, fields: [...p.fields, field] })); selectField(field.id); markUnsaved();
  };
  const addTable = () => {
    const table = { id: nextId("t", schemaDraft.tables.map((t) => t.id)), name: uniqueName("New Table", schemaDraft.tables.map((t) => t.name)), description: "", columns: [{ id: "c1", name: "New Column", type: "string" }] };
    setSchemaDraft((p) => ({ ...p, tables: [...p.tables, table] })); selectTable(table.id); markUnsaved();
  };
  const updateField = (id: string, patch: Partial<SchemaField>) => { setSchemaDraft((p) => ({ ...p, fields: p.fields.map((f) => f.id === id ? { ...f, ...patch } : f) })); markUnsaved(); };
  const updateTable = (id: string, patch: Partial<SchemaTable>) => { setSchemaDraft((p) => ({ ...p, tables: p.tables.map((t) => t.id === id ? { ...t, ...patch } : t) })); markUnsaved(); };
  const addColumn = (tableId: string) => {
    setSchemaDraft((p) => ({ ...p, tables: p.tables.map((t) => t.id !== tableId ? t : { ...t, columns: [...t.columns, { id: nextId("c", t.columns.map((c) => c.id)), name: uniqueName("New Column", t.columns.map((c) => c.name)), type: "string" }] }) }));
    markUnsaved();
  };
  const updateColumn = (tableId: string, columnId: string, patch: Partial<SchemaColumn>) => {
    setSchemaDraft((p) => ({ ...p, tables: p.tables.map((t) => t.id !== tableId ? t : { ...t, columns: t.columns.map((c) => c.id === columnId ? { ...c, ...patch } : c) }) }));
    markUnsaved();
  };
  const deleteColumn = (tableId: string, columnId: string) => {
    setSchemaDraft((p) => ({ ...p, tables: p.tables.map((t) => t.id !== tableId ? t : { ...t, columns: t.columns.filter((c) => c.id !== columnId) }) }));
    markUnsaved();
  };
  const deleteField = (fieldId: string) => {
    const idx = schemaDraft.fields.findIndex((f) => f.id === fieldId); if (idx < 0) return;
    const next = schemaDraft.fields.filter((f) => f.id !== fieldId); setSchemaDraft((p) => ({ ...p, fields: next }));
    if (selectedFieldId === fieldId) next.length ? selectField(next[Math.max(0, idx - 1)].id) : schemaDraft.tables.length ? selectTable(schemaDraft.tables[0].id) : (setSelectedMode(null), setSelectedFieldId(null), setSelectedTableId(null));
    markUnsaved();
  };
  const deleteTable = (tableId: string) => {
    const idx = schemaDraft.tables.findIndex((t) => t.id === tableId); if (idx < 0) return;
    const next = schemaDraft.tables.filter((t) => t.id !== tableId); setSchemaDraft((p) => ({ ...p, tables: next }));
    if (selectedTableId === tableId) next.length ? selectTable(next[Math.max(0, idx - 1)].id) : schemaDraft.fields.length ? selectField(schemaDraft.fields[0].id) : (setSelectedMode(null), setSelectedFieldId(null), setSelectedTableId(null));
    markUnsaved();
  };

  const discardChanges = () => { applySnapshot(schemaId, loadedSchemaName, loadedDocumentType, cloneSchema(loadedSnapshot), schemaId ? "Loaded from backend." : "Unsaved schema draft."); setError(null); };
  const saveSchema = async () => {
    if (!projectId) return setError("Missing project id in route.");
    if (!schemaName.trim()) return setError("Schema name is required.");
    setSaving(true); setError(null);
    try {
      const payload = toPayload(schemaName, documentType, schemaDraft);
      const saved = schemaId ? await updateExtractionSchema(schemaId, payload) : await createExtractionSchema(projectId, payload);
      applySnapshot(saved.schema_id, saved.name, saved.document_type || "", toDraft(saved), "Schema saved to backend.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save schema.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <header className="px-6 py-4 border-b border-border bg-surface flex items-center justify-between shrink-0">
        <div><h1 className="text-xl font-semibold tracking-tight text-text-primary">Extraction Schema Builder</h1><p className="text-xs text-text-secondary mt-1">Define the structure to extract from your documents.</p></div>
        <div className="flex gap-2"><Button variant="outline" onClick={discardChanges}>Discard Changes</Button><Button variant="primary" onClick={() => void saveSchema()} disabled={saving || loading}>{saving ? "Saving..." : "Save Schema"}</Button></div>
      </header>

      <div className="flex-1 flex flex-col p-6 overflow-hidden">
        <div className="max-w-6xl mx-auto w-full flex-1 flex gap-6 min-h-0">
          <div className="w-80 flex flex-col gap-4 border-r border-border pr-6 shrink-0 overflow-y-auto">
            <div className="flex items-center justify-between"><h3 className="text-[11px] font-bold text-text-secondary uppercase tracking-wider">Fields</h3><Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-text-secondary" onClick={addField}><Plus className="h-4 w-4" /></Button></div>
            <div className="space-y-1">{schemaDraft.fields.map((field) => <div key={field.id} onClick={() => selectField(field.id)} className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm cursor-pointer transition-colors ${selectedMode === "field" && selectedFieldId === field.id ? "bg-primary/20 text-primary font-medium" : "hover:bg-surface-muted text-text-primary"}`}><List className={`h-4 w-4 ${selectedMode === "field" && selectedFieldId === field.id ? "text-primary" : "text-text-secondary"}`} /><span className="flex-1 truncate">{field.name}</span>{field.required && <span className="text-[9px] bg-warning/20 text-warning px-1.5 py-0.5 rounded font-bold uppercase tracking-wider">Req</span>}</div>)}</div>
            <div className="flex items-center justify-between mt-4"><h3 className="text-[11px] font-bold text-text-secondary uppercase tracking-wider">Tables</h3><Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-text-secondary" onClick={addTable}><Plus className="h-4 w-4" /></Button></div>
            <div className="space-y-1">{schemaDraft.tables.map((table) => <div key={table.id} onClick={() => selectTable(table.id)} className={`flex flex-col gap-1 px-3 py-1.5 rounded cursor-pointer transition-colors ${selectedMode === "table" && selectedTableId === table.id ? "bg-primary/20" : "hover:bg-surface-muted"}`}><div className={`flex items-center gap-2 text-sm ${selectedMode === "table" && selectedTableId === table.id ? "text-primary font-medium" : "text-text-primary"}`}><Database className={`h-4 w-4 ${selectedMode === "table" && selectedTableId === table.id ? "text-primary" : "text-text-secondary"}`} /><span className="flex-1 truncate">{table.name}</span></div><div className="pl-6 space-y-1 border-l border-primary/30 ml-2 mt-1">{table.columns.map((column) => <div key={column.id} className="text-xs text-text-secondary">{column.name}</div>)}</div></div>)}</div>
          </div>

          <div className="flex-1 overflow-y-auto pb-6 space-y-3">
            <Card className="max-w-2xl border border-cyan-500/30 bg-cyan-500/10">
              <CardContent className="p-3 space-y-2">
                <p className="text-xs text-cyan-200">{statusNote}</p>
                {error && <p className="text-xs text-red-300">{error}</p>}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <Input value={schemaName} onChange={(e) => { setSchemaName(e.target.value); markUnsaved(); }} placeholder="Schema name" className="text-[13px]" />
                  <Input value={documentType} onChange={(e) => { setDocumentType(e.target.value); markUnsaved(); }} placeholder="Document type" className="text-[13px]" />
                </div>
              </CardContent>
            </Card>

            {selectedMode === "field" && selectedField ? (
              <Card className="max-w-2xl">
                <CardContent className="p-5 space-y-6">
                  <div className="flex items-center justify-between"><h2 className="text-sm font-bold uppercase tracking-wider text-text-secondary">Edit Field</h2><Button variant="ghost" size="sm" className="text-text-secondary hover:text-danger" onClick={() => deleteField(selectedField.id)}><Trash2 className="h-4 w-4" /></Button></div>
                  <div className="space-y-4">
                    <div className="space-y-1"><label className="block text-[11px] font-bold text-text-secondary uppercase tracking-wider">Display Name</label><Input value={selectedField.name} onChange={(e) => updateField(selectedField.id, { name: e.target.value })} className="text-[13px]" /></div>
                    <div className="space-y-1"><label className="block text-[11px] font-bold text-text-secondary uppercase tracking-wider">Description</label><textarea className="w-full text-[13px] rounded-md border border-border bg-surface px-3 py-2 text-text-primary focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary transition-colors h-20" value={selectedField.description ?? ""} onChange={(e) => updateField(selectedField.id, { description: e.target.value })} /></div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1"><label className="block text-[11px] font-bold text-text-secondary uppercase tracking-wider">Data Type</label><select className="w-full text-[13px] rounded-md border border-border bg-surface px-3 py-2 text-text-primary focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary transition-colors" value={selectedField.type} onChange={(e) => updateField(selectedField.id, { type: e.target.value })}><option value="string">String</option><option value="number">Number</option><option value="currency">Currency</option><option value="date">Date</option></select></div>
                      <div className="space-y-2 flex flex-col justify-end"><label className="flex items-center gap-2 text-sm font-medium text-text-primary h-9 cursor-pointer"><input type="checkbox" className="rounded border-border text-primary focus:ring-primary bg-surface/50" checked={selectedField.required} onChange={(e) => updateField(selectedField.id, { required: e.target.checked })} /><span className="text-[13px]">Required Field</span></label></div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ) : selectedMode === "table" && selectedTable ? (
              <Card className="max-w-2xl">
                <CardContent className="p-5 space-y-6">
                  <div className="flex items-center justify-between"><h2 className="text-sm font-bold uppercase tracking-wider text-text-secondary">Edit Table</h2><Button variant="ghost" size="sm" className="text-text-secondary hover:text-danger" onClick={() => deleteTable(selectedTable.id)}><Trash2 className="h-4 w-4" /></Button></div>
                  <div className="space-y-4">
                    <div className="space-y-1"><label className="block text-[11px] font-bold text-text-secondary uppercase tracking-wider">Table Name</label><Input value={selectedTable.name} onChange={(e) => updateTable(selectedTable.id, { name: e.target.value })} className="text-[13px]" /></div>
                    <div className="space-y-2">
                      <label className="block text-[11px] font-bold text-text-secondary uppercase tracking-wider">Columns</label>
                      <div className="border border-border rounded divide-y divide-border/50 bg-surface">{selectedTable.columns.map((column) => <div key={column.id} className="p-2 flex items-center justify-between bg-surface-muted/50 hover:bg-surface-muted transition-colors"><div className="flex gap-2 flex-1"><Input value={column.name} onChange={(e) => updateColumn(selectedTable.id, column.id, { name: e.target.value })} className="bg-surface h-8 text-[13px]" /><select className="rounded border border-border bg-surface px-2 h-8 text-[13px] focus:outline-none focus:ring-1 focus:ring-primary text-text-primary" value={column.type} onChange={(e) => updateColumn(selectedTable.id, column.id, { type: e.target.value })}><option value="string">String</option><option value="number">Number</option><option value="currency">Currency</option><option value="date">Date</option></select></div><div className="flex ml-2 gap-1"><Button variant="ghost" size="sm" className="h-8 w-8 text-text-secondary hover:text-danger p-0" onClick={() => deleteColumn(selectedTable.id, column.id)}><Trash2 className="h-4 w-4" /></Button></div></div>)}</div>
                      <Button variant="outline" size="sm" className="mt-2 w-full border-dashed" onClick={() => addColumn(selectedTable.id)}><Plus className="mr-1.5 h-4 w-4" /> Add Column</Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-text-secondary"><List className="h-10 w-10 mb-4 opacity-20" /><p className="text-sm">Select a field or table to edit</p></div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
