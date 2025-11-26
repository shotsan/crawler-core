# Three Sites Test Results

## Test Summary
- **Total Sites**: 3
- **Total Execution Time**: 110.80 seconds
- **Success Rate**: 100% (3/3 successful)
- **Total Selectors Discovered**: 123 (39 + 40 + 44)

---

## 1. Alo Yoga (www.aloyoga.com)

### Phase 1.5 Discovery:
- **HTML Analysis**: 4 selectors discovered
  - `[role="dialog"]` (modal)
  - `[aria-modal="true"]` (modal)
  - `button:contains("cookie policy")` (accept_button)
  - `#48de3afd-262a-4713-ae5c-97b06c0b1300` (accept_button)
- **DOM Analysis**: 40 high z-index overlays discovered
  - `.osano-cm-window` (Osano cookie manager)
  - `#92129ad2-d81b-46e8-b7b7-81c7920f7c37`
  - `#videoModal`
  - Many navigation/header elements
- **Total**: 44 selectors discovered

### Phase 2 Popup Handling:
- **High-Priority Selectors**: 8 (cookie/modal/overlay related)
- **Other Selectors**: 36
- **Result**: ✅ Successfully handled popups

---

## 2. Victoria's Secret (www.victoriassecret.com)

### Phase 1.5 Discovery:
- **HTML Analysis**: 5 selectors discovered
  - `.onetrust-banner-container` (cookie_framework)
  - `[role="dialog"]` (modal)
  - `[aria-modal="true"]` (modal)
  - `button:contains("ok")` (accept_button)
  - `.onetrust` (cookie_script)
- **DOM Analysis**: 35 high z-index overlays discovered
  - `#onetrust-pc-sdk` (OneTrust preference center)
  - `#ot-anchor`, `#ot-fltr-cnt` (OneTrust elements)
  - Many styled-components (`.sc-*`)
- **Total**: 40 selectors discovered

### Phase 2 Popup Handling:
- **High-Priority Selectors**: 7 (OneTrust/cookie related)
- **Other Selectors**: 33
- **Key Actions**:
  - ✅ Found and clicked buttons in `#onetrust-banner-sdk`
  - ✅ Checked all discovered high z-index selectors including `#onetrust-pc-sdk`
  - ✅ Aggressive cleanup removed 1 OneTrust element
  - ✅ Cookie banner verification: No visible banners found
- **Result**: ✅ Successfully handled popups

---

## 3. Longines (www.longines.com)

### Phase 1.5 Discovery:
- **HTML Analysis**: 1 selector discovered
  - `#usercentrics-root` (cookie_script - Usercentrics)
- **DOM Analysis**: 38 high z-index overlays discovered
  - `.SkipToMainContent_SkipToMainContent__XE5HC`
  - `.Header_Toolbar__8JmKF`, `.Header_Sticky__j9dbC` (header elements)
  - `.CloseButton_Button__I2OMq` (close button!)
  - `.Dialog_Head__hF57z` (dialog element)
- **Total**: 39 selectors discovered

### Phase 2 Popup Handling:
- **High-Priority Selectors**: 2 (Usercentrics/cookie related)
- **Other Selectors**: 37
- **Key Actions**:
  - ✅ Found and clicked accept button using fallback pattern
  - ✅ Aggressive cleanup: 0 OneTrust elements (not OneTrust, it's Usercentrics)
  - ✅ Cookie banner verification: No visible banners found
- **Result**: ✅ Successfully handled popups

---

## Key Improvements Demonstrated:

1. **No Confidence Filtering**: All discovered selectors are tried, not just "high confidence" ones
2. **All Selectors Checked**: System checks ALL discovered selectors (not just first few)
3. **High Z-Index Prioritization**: High z-index selectors are checked first (strong popup indicators)
4. **No Early Returns**: Continues checking all selectors even after first success (some sites have multiple popups)
5. **Better Discovery**: Found important selectors like:
   - `#onetrust-pc-sdk` (Victoria's Secret)
   - `.osano-cm-window` (Alo Yoga)
   - `.CloseButton_Button__I2OMq` (Longines)

---

## Performance:
- **Pages per second**: 0.03
- **Websites per minute**: 1.62
- **All sites completed successfully**: ✅
