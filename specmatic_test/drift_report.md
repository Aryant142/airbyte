# Contract Validation Report

**Overall Build Status: FAIL**

## Streams Tested

| Stream          | Request Validation | Response Schema Validation  | Status   |
| :---            | :---:              | :---:                       | :---:    |
| customers       | ✅                 | ❌                         | **FAIL** |
| charges         | ✅                 | ✅                         | **PASS** |
| invoices        | ✅                 | ✅                         | **PASS** |
| payment_intents | ✅                 | ✅                         | **PASS** |
| products        | ✅                 | ✅                         | **PASS** |
| prices          | ✅                 | ✅                         | **PASS** |
| refunds         | ✅                 | ✅                         | **PASS** |

## Contract Violations

### Stream: `customers`
- **Response Schema Mismatch**: Field 'root': 'email' is a required property

