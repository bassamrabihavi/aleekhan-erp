// Page 40 «اسناد» (MOCK_UI_BINDING §6.3): document list, revisions with scan status, upload into quarantine
// (DEC-053), download only when CLEAN (always as an attachment, never shown in the browser), submit / approve /
// reject. Check-out/check-in and the hash-error counter are not adopted (C-46).
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { apiRequest } from "../api/http";
import { docGuards, read, write, type DocumentItem, type DocumentRevision } from "../api/phase01";
import { useAuth } from "../auth/context";
import { ActionError } from "../components/ActionError";
import { DataView } from "../components/DataView";
import { Dialog } from "../components/Dialog";
import { Field, ReasonDialog, ShortId } from "../components/Form";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime, toFaDigits } from "../lib/format";
import { REVISION_STATUS, SCAN_STATUS, toneLabel } from "../lib/labels";
import { QK, useCursor } from "../lib/queries";
import { navigate, segments, useRoute } from "../lib/router";
import { useAction } from "../lib/useAction";
import { Pager } from "./SecurityPage";

const D = {
  create: "platform.document.create",
  update: "platform.document.update",
  upload: "platform.document.upload",
  approve: "platform.document.approve",
  download: "platform.document.download",
};
/** Allow-list of DEC-053 (the server is authoritative; this only pre-filters the file picker). */
const ACCEPT = ".pdf,.png,.jpg,.jpeg,.dxf,.xlsx";

export function DocumentsPage() {
  const route = useRoute();
  const [docId] = segments(route, "/documents");
  return (
    <div className="page" data-testid="page-documents">
      <div className="page__head">
        <div>
          <p className="eyebrow">صفحه ۴۰ · فاز ۱</p>
          <h1>اسناد</h1>
          <p className="lead">
            هر فایل بارگذاری‌شده ابتدا قرنطینه می‌شود و فقط پس از بررسی ضدبدافزار و وضعیت «پاک» قابل دانلود است. فایل‌ها
            در مرورگر باز یا اجرا نمی‌شوند (DEC-053).
          </p>
        </div>
      </div>
      {docId ? <DocumentDetail documentId={docId} /> : <DocumentList />}
    </div>
  );
}

function DocumentList() {
  const { can } = useAuth();
  const [type, setType] = useState("");
  const [filter, setFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const cursor = useCursor();
  const list = useQuery({
    queryKey: [...QK.documents, "list", filter, cursor.cursor],
    queryFn: async ({ signal }) =>
      (await read("/documents", docGuards.docPage, { document_type: filter, cursor: cursor.cursor, page_size: 25 }, signal)).data,
  });
  return (
    <section className="panel panel--wide" aria-labelledby="docs-title">
      <div className="panel__head">
        <h2 id="docs-title">فهرست اسناد</h2>
        {can(D.create) ? <button type="button" className="btn btn--primary" onClick={() => { setCreating(true); }} data-testid="doc-create-open">ثبت سند</button> : null}
      </div>
      <form className="filters" role="search" onSubmit={(e) => { e.preventDefault(); cursor.reset(); setFilter(type.trim()); }}>
        <Field label="نوع سند (کلید سیستمی)">
          {(id) => <input id={id} className="input" dir="ltr" value={type} onChange={(e) => { setType(e.target.value); }} data-testid="doc-type-filter" />}
        </Field>
        <button type="submit" className="btn btn--secondary">فیلتر</button>
      </form>
      <DataView query={list} loading="در حال دریافت اسناد…" errorTitle="اسناد دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "سندی در دسترس شما نیست.", hint: "اسناد طبق نقش و سطح محرمانگی (S1–S3) نمایش داده می‌شوند." }}>
        {(d) => (
          <>
            <table className="table table--cards" data-testid="documents-table">
              <caption className="sr-only">فهرست اسناد</caption>
              <thead>
                <tr>
                  <th scope="col">عنوان</th>
                  <th scope="col">نوع</th>
                  <th scope="col">محرمانگی</th>
                  <th scope="col">مالک (موجودیت)</th>
                  <th scope="col">نسخه تأییدشده</th>
                  <th scope="col">ثبت</th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((doc) => (
                  <tr key={doc.document_id}>
                    <td data-label="عنوان"><a href={`#/documents/${doc.document_id}`} data-testid="doc-link">{doc.title_fa}</a></td>
                    <td data-label="نوع"><code dir="ltr">{doc.document_type}</code></td>
                    <td data-label="محرمانگی"><bdi dir="ltr">{doc.sensitivity ?? "—"}</bdi></td>
                    <td data-label="مالک (موجودیت)">{doc.owner_entity ? <><code dir="ltr">{doc.owner_entity.entity_type}</code> <code dir="ltr">{doc.owner_entity.entity_id}</code></> : "—"}</td>
                    <td data-label="نسخه تأییدشده">{doc.current_approved_revision_id ? <ShortId id={doc.current_approved_revision_id} /> : "ندارد"}</td>
                    <td data-label="ثبت">{formatJalaliDateTime(doc.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager depth={cursor.depth} next={d.page.next_cursor} onNext={cursor.next} onPrev={cursor.prev} />
          </>
        )}
      </DataView>
      {creating ? <CreateDocumentDialog onClose={() => { setCreating(false); }} /> : null}
    </section>
  );
}

function CreateDocumentDialog({ onClose }: { onClose: () => void }) {
  const action = useAction();
  const [f, setF] = useState({ document_type: "", title_fa: "", sensitivity: "S1", entity_type: "", entity_id: "", legacy: "" });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => { setF((x) => ({ ...x, [k]: e.target.value })); };
  return (
    <Dialog title="ثبت سند" onClose={onClose} testId="doc-create-dialog">
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          const body: Record<string, unknown> = { document_type: f.document_type.trim(), title_fa: f.title_fa.trim(), sensitivity: f.sensitivity };
          if (f.entity_type.trim() && f.entity_id.trim()) body.owner_entity = { entity_type: f.entity_type.trim(), entity_id: f.entity_id.trim() };
          if (f.legacy.trim()) body.legacy_location_ref = f.legacy.trim();
          void action.run((key) => write("/documents", docGuards.doc, body, key), [QK.documents]).then((r) => {
            if (r) {
              onClose();
              navigate(`/documents/${r.data.document_id}`);
            }
          });
        }}
      >
        <Field label="نوع سند (کلید سیستمی، مثل drawing)">{(id) => <input id={id} className="input" dir="ltr" required pattern="[a-z][a-z0-9_]*" value={f.document_type} onChange={set("document_type")} data-testid="doc-type" />}</Field>
        <Field label="عنوان">{(id) => <input id={id} className="input" required maxLength={200} value={f.title_fa} onChange={set("title_fa")} data-testid="doc-title" />}</Field>
        <Field label="سطح محرمانگی">
          {(id) => (
            <select id={id} className="input" value={f.sensitivity} onChange={set("sensitivity")}>
              <option value="S1">S1 — عمومی داخلی</option>
              <option value="S2">S2 — محدود</option>
              <option value="S3">S3 — محرمانه</option>
            </select>
          )}
        </Field>
        <Field label="نوع موجودیت مالک (اختیاری)">{(id) => <input id={id} className="input" dir="ltr" value={f.entity_type} onChange={set("entity_type")} />}</Field>
        <Field label="شناسه موجودیت مالک (مثلاً کد ۱۴ رقمی؛ صفرهای ابتدا حفظ می‌شود)">{(id) => <input id={id} className="input" dir="ltr" inputMode="numeric" value={f.entity_id} onChange={set("entity_id")} />}</Field>
        <Field label="مرجع قدیمی (فقط متن، مثل مسیر پوشه قبلی)">{(id) => <input id={id} className="input" dir="ltr" maxLength={500} value={f.legacy} onChange={set("legacy")} />}</Field>
        <ActionError error={action.error} />
        <div className="form__actions">
          <button type="submit" className="btn btn--primary" disabled={action.pending} data-testid="doc-create-submit">{action.pending ? "در حال ثبت…" : "ثبت سند"}</button>
          <button type="button" className="btn btn--secondary" onClick={onClose}>انصراف</button>
        </div>
      </form>
    </Dialog>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${toFaDigits(n)} بایت`;
  if (n < 1024 * 1024) return `${toFaDigits((n / 1024).toFixed(1))} کیلوبایت`;
  return `${toFaDigits((n / 1024 / 1024).toFixed(1))} مگابایت`;
}

function DocumentDetail({ documentId }: { documentId: string }) {
  const { can } = useAuth();
  const doc = useQuery({
    queryKey: [...QK.documents, "detail", documentId],
    queryFn: async ({ signal }) => (await read(`/documents/${documentId}`, docGuards.doc, undefined, signal)).data,
  });
  const revs = useQuery({
    queryKey: [...QK.documents, "revisions", documentId],
    queryFn: async ({ signal }) => (await read(`/documents/${documentId}/revisions`, docGuards.revPage, { page_size: 100 }, signal)).data,
  });
  return (
    <>
      <p><a href="#/documents">بازگشت به فهرست اسناد</a></p>
      <DataView query={doc} loading="در حال دریافت سند…" errorTitle="سند دریافت نشد">
        {(d: DocumentItem) => (
          <section className="panel panel--wide" aria-labelledby="doc-title" data-testid="document-detail">
            <h2 id="doc-title">{d.title_fa}</h2>
            <dl className="meta">
              <div><dt>نوع</dt><dd><code dir="ltr">{d.document_type}</code></dd></div>
              <div><dt>محرمانگی</dt><dd><bdi dir="ltr">{d.sensitivity ?? "—"}</bdi></dd></div>
              {d.owner_entity ? <div><dt>موجودیت مالک</dt><dd><code dir="ltr">{d.owner_entity.entity_type}</code> <code dir="ltr">{d.owner_entity.entity_id}</code></dd></div> : null}
              {d.legacy_location_ref ? <div><dt>مرجع قدیمی (فقط متن)</dt><dd><code dir="ltr">{d.legacy_location_ref}</code></dd></div> : null}
            </dl>
          </section>
        )}
      </DataView>
      <section className="panel panel--wide" aria-labelledby="revs-title">
        <h2 id="revs-title">نسخه‌ها</h2>
        {can(D.upload) ? <UploadForm documentId={documentId} latest={revs.data?.items.reduce<DocumentRevision | null>((m, r) => (!m || r.revision_no > m.revision_no ? r : m), null) ?? null} /> : null}
        <DataView query={revs} loading="در حال دریافت نسخه‌ها…" errorTitle="نسخه‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "هنوز نسخه‌ای بارگذاری نشده است." }}>
          {(d) => <RevisionTable documentId={documentId} items={[...d.items].sort((a, b) => b.revision_no - a.revision_no)} />}
        </DataView>
      </section>
    </>
  );
}

function UploadForm({ documentId, latest }: { documentId: string; latest: DocumentRevision | null }) {
  const action = useAction();
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [inputKey, setInputKey] = useState(0);
  const [done, setDone] = useState<DocumentRevision | null>(null);
  return (
    <form
      className="form form--inline"
      onSubmit={(e) => {
        e.preventDefault();
        if (!file) return;
        setDone(null);
        void action
          .run((key) => {
            const form = new FormData();
            form.set("file", file, file.name);
            if (note.trim()) form.set("change_note", note.trim());
            if (latest) form.set("parent_revision_id", latest.revision_id);
            return apiRequest(`/documents/${documentId}/revisions`, docGuards.rev, { method: "POST", form, idempotencyKey: key });
          }, [QK.documents])
          .then((r) => {
            if (r) {
              setDone(r.data);
              setFile(null);
              setNote("");
              setInputKey((k) => k + 1);
            }
          });
      }}
      data-testid="upload-form"
    >
      <Field label="فایل نسخه تازه" hint="مجاز: PDF، PNG، JPG، DXF، XLSX بدون ماکرو؛ حداکثر ۲۵ مگابایت (DEC-053).">
        {(id, hintId) => <input key={inputKey} id={id} aria-describedby={hintId} className="input" type="file" accept={ACCEPT} required onChange={(e) => { setFile(e.target.files?.[0] ?? null); }} data-testid="upload-file" />}
      </Field>
      <Field label="یادداشت تغییر (اختیاری)">{(id) => <input id={id} className="input" maxLength={500} value={note} onChange={(e) => { setNote(e.target.value); }} data-testid="upload-note" />}</Field>
      <p className="field__hint">{latest ? `بر پایه آخرین نسخه (نسخه ${toFaDigits(latest.revision_no)})؛ اگر کسی هم‌زمان نسخه تازه‌تری ثبت کند، سرور این بارگذاری را رد می‌کند.` : "نخستین نسخه این سند."}</p>
      <ActionError error={action.error} />
      {done ? (
        <p className="notice notice--info" role="status" data-testid="upload-done">
          نسخه {toFaDigits(done.revision_no)} دریافت شد و در وضعیت «{toneLabel(SCAN_STATUS, done.scan_status).label}» است؛ تا پاک‌شدن قابل دانلود نیست.
        </p>
      ) : null}
      <button type="submit" className="btn btn--primary" disabled={action.pending || !file} data-testid="upload-submit">{action.pending ? "در حال بارگذاری…" : "بارگذاری در قرنطینه"}</button>
    </form>
  );
}

type RevOp = "submit" | "approve" | "reject";

function RevisionTable({ documentId, items }: { documentId: string; items: DocumentRevision[] }) {
  const { can } = useAuth();
  const action = useAction();
  const [op, setOp] = useState<{ rev: DocumentRevision; op: RevOp } | null>(null);
  return (
    <>
      <ActionError error={op ? null : action.error} />
      <table className="table table--cards" data-testid="revisions-table">
        <caption className="sr-only">نسخه‌های سند</caption>
        <thead>
          <tr>
            <th scope="col">نسخه</th>
            <th scope="col">وضعیت</th>
            <th scope="col">بررسی ضدبدافزار</th>
            <th scope="col">فایل</th>
            <th scope="col">هش SHA-256</th>
            <th scope="col">بارگذاری</th>
            <th scope="col"><span className="sr-only">اقدام</span></th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => {
            const st = toneLabel(REVISION_STATUS, r.status);
            const sc = toneLabel(SCAN_STATUS, r.scan_status);
            const clean = r.scan_status === "CLEAN";
            return (
              <tr key={r.revision_id} data-testid={`revision-${r.revision_no}`}>
                <td data-label="نسخه">{toFaDigits(r.revision_no)}</td>
                <td data-label="وضعیت"><StatusChip tone={st.tone} label={st.label} /></td>
                <td data-label="بررسی ضدبدافزار"><StatusChip tone={sc.tone} label={sc.label} testId="scan-status" /></td>
                <td data-label="فایل"><bdi dir="ltr">{r.original_name}</bdi> · {formatBytes(r.size_bytes)} · <code dir="ltr">{r.media_type}</code>{r.change_note ? <p className="field__hint">{r.change_note}</p> : null}</td>
                <td data-label="هش SHA-256"><code dir="ltr" className="code-id" title={r.sha256}>{r.sha256.slice(0, 16)}…</code></td>
                <td data-label="بارگذاری">{formatJalaliDateTime(r.uploaded_at)}</td>
                <td data-label="اقدام">
                  <div className="actions">
                    {can(D.download) ? (
                      clean ? (
                        <a className="btn btn--secondary" href={`/api/v1/documents/${documentId}/revisions/${r.revision_id}/content`} download data-testid="download">دانلود</a>
                      ) : (
                        <button type="button" className="btn btn--secondary" disabled aria-describedby={`dl-${r.revision_id}`} data-testid="download-disabled">دانلود</button>
                      )
                    ) : null}
                    {can(D.download) && !clean ? <span id={`dl-${r.revision_id}`} className="field__hint">فقط نسخه پاک قابل دانلود است</span> : null}
                    {can(D.update) && r.status === "WORKING" ? <button type="button" className="btn btn--secondary" onClick={() => { action.reset(); setOp({ rev: r, op: "submit" }); }} data-testid="rev-submit">ارسال برای بازبینی</button> : null}
                    {can(D.approve) && r.status === "IN_REVIEW" ? (
                      <>
                        <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setOp({ rev: r, op: "approve" }); }}>تأیید</button>
                        <button type="button" className="btn btn--danger-outline" onClick={() => { action.reset(); setOp({ rev: r, op: "reject" }); }}>رد</button>
                      </>
                    ) : null}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {op ? (
        <ReasonDialog
          title={{ submit: "ارسال برای بازبینی", approve: "تأیید نسخه", reject: "رد نسخه" }[op.op]}
          label={op.op === "reject" ? "دلیل رد" : "یادداشت (در ممیزی ثبت می‌شود)"}
          minLength={op.op === "reject" ? 3 : 1}
          submitLabel={{ submit: "ارسال", approve: "تأیید", reject: "رد" }[op.op]}
          danger={op.op === "reject"}
          action={action}
          onClose={() => { setOp(null); }}
          onSubmit={async (text) => {
            const path = `/documents/${documentId}/revisions/${op.rev.revision_id}/${op.op === "submit" ? "submit-review" : op.op}`;
            const body = op.op === "reject" ? { reason: text } : { note: text };
            return (await action.run((key) => write(path, docGuards.rev, body, key, op.rev.row_version), [QK.documents])) !== undefined;
          }}
        />
      ) : null}
    </>
  );
}
