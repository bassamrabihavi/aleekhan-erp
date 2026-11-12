# Planning workbook extraction summary (DEC-005 / DEC-006)

**Source:** `Planning--.xlsm`, intake sha `113f5400…`; see `control/SOURCE_INTAKE.csv`. The employer confirmed it as the golden baseline on 2026-11-12, which amends DEC-037.

**How it was read:**
- On work-windows, from `ALEEKHAN_PRIVATE_DIR`.
- Decrypted in memory, and opened with openpyxl (no VBA engine).
- VBA was parsed as text with oletools and **never executed**.

**What this file contains, and what it does not:**
- Aggregate counts, and rule structure taken from the formulas.
- **No real code, serial, customer, person or row values.** Those, with their cell addresses, are only in the private report under `F:/aleekhan/private-extract/` (outside the repo, never committed).
- Examples are synthetic.

## Serial (DEC-006), from `NOrder!B`
- **Count:** 3,920 entries, typed in by hand, with no formula.
- **Next serial:** the legacy rule in `Order form!F7` is `MAX(NOrder!B)+1`, with a floor at 60000. This is C-49 / R-13 (not safe with several users), and the new system replaces it.
- **Shapes:**

  | Shape | Count |
  |---|---|
  | Plain integer (no prefix, no leading zero) | 3,779 |
  | `S` + number | 40 |
  | `-digit` suffix | 85 |
  | `-P` suffix | 13 |
  | `-N` suffix | 2 |
  | `BG` prefix | 1 |
  | Duplicated values | 2 |

- **Legacy maximum:** below 63000.
- **Decision:** see DECISION_LOG, 2026-11-12. Serials are plain integers starting at 63001. The legacy variants are history only.

## 14-digit product code (DEC-005)

### E-1 / E-5: the code formula and the stored values
`NOrder!FZ` uses **one** formula variant in all 3,855 formula rows:

```
"02" & TypeCode(ProductType) & CategoryCode & ProductNo(4) & StyleNo(4)
```

- `TypeCode` is looked up from `Sorce!O`, matched on product type in `Sorce!E`.
- `CategoryCode` is `NOrder!FY`. FY is itself one formula variant: it looks up `Sorce!O` in the category column for that type (`Sorce!BE..BI`).
- Synthetic example: `02 01 07 9001 0003`.

Stored values:
- 3,917 values, **all text**, so no leading zeros were lost.
- 3,283 values are exactly 14 digits.
- 634 values are not 14 digits:

  | Cause | Rows |
  |---|---|
  | Style is not 4 digits (`*`, `A-9999`, short) | 430 |
  | Product and style not 4 digits | 30 |
  | No category, and product and style not 4 digits | 130 |
  | No category, and style not 4 digits | 24 |
  | No category only | 20 |
  | Product not 4 digits only | 3 |

### E-2: `Sorce` sheet
- 10 product types in `E`.
- 50 two-digit codes in `O`. All are text and none is duplicated.

### E-3: `NOrder` columns

| Column | Header | Values |
|---|---|---|
| `A` | product type | text, manual |
| `C` | product number | 4-digit text in 3,757 rows |
| `D` | style number | 4-digit text in 3,306 rows |
| `FY` | category code | 2-digit, from formula |

### E-4 / E-8: how numbers are assigned (`Order form`, macro `Codding`, text only)

**Product number** (`Order form!J10`), in priority order:
1. If the user enters one, it is used.
2. **Belt:** the buckle-type code (from `Sorce!O` via `Sorce!BN`) followed by the belt width.
3. **New product:** `MAXIFS(Codding!R, Codding!C = product type) + 1`, so a new product gets the next number per product type.
4. **Existing product:** looked up in `Codding`.

**Style number** (`Order form!J11`):
- If the user enters one, it is used.
- Otherwise it is `COUNTIFS(Codding!A = product, Codding!D = category) + 1`, zero-padded to 4 digits. So styles count from 0001 for each product within each category.

**Macro `Codding`:**
- It appends the new row (`OrderSorce!C28:S28`) to `Codding`.
- It refuses a style key that already exists (`OrderSorce!B29`).

**Note for the reviewer (C-77):** the code preview in `Order form!J5` takes the category code from `Sorce!A` via `Sorce!BZ`. `NOrder!FY` takes it from `Sorce!O` via the type-specific column. Golden tests must check that both give the same code.

### E-6: codes and styles
- 2,534 distinct codes in `NOrder!FZ`; 624 codes appear on more than one order row, as expected.
- 8 codes map to more than one (product, style) pair. These are flagged.
- 820 distinct product numbers; 51 of them are used in more than one (type, category).
- Of 915 (type, category, product) groups, 796 have styles starting at 0001, and 803 have contiguous style runs.

### E-7: families (golden ≥20 cases)
"Family" = **product type** (decided 2026-11-12). Distinct 14-digit codes per type code:

| Type code | Distinct codes |
|---|---|
| 01 | 1,215 |
| 02 | 364 |
| 03 | 302 |
| 05 | 253 |
| 04 | 179 |

All five types meet the minimum of 20. By category it would be only 17 of 36.

### E-9 / E-10: the prefix `02` and Rahkaran
- The Rahkaran item list held in `Codding` has 1,995 codes. **All** start with `02`, so `02` is the product nature.
- The workbook already checks for each code whether it is registered in Rahkaran (`Order form!J4`).
- 793 of the 2,313 distinct 14-digit NOrder codes are found in that list. The list in the workbook may be a partial export; the real Rahkaran import in PHASE_02 decides.
- 2,169 of the 2,313 are found in `Codding`.

### E-11
`planning_coding_audit_v01.md` is not in the private folder. C-73 stays open (evidence gap only).
