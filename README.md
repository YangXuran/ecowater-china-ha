# Ecowater China (怡口智控) — Home Assistant Integration

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.5%2B-41BDF5)](https://www.home-assistant.io/)

Reverse-engineered Home Assistant custom integration for **Ecowater (怡口) V80ECM water softener** via the WeChat mini-program cloud API (`iot2.chinaecowater.com`).

> ⚠️ **This is an unofficial community reverse-engineering project.** Not affiliated with Ecowater or 怡口中国. Use at your own risk.

## Features

- 🌊 **9 sensors** — flow rate, water volume, regeneration status, hardness
- 🔄 **Regeneration tracking** — real-time stage monitoring (backwash → brine draw → rinse)
- 📊 **Daily statistics** — daily water usage and averages
- ⚡ **Regeneration button** — trigger immediate regeneration from HA dashboard
- 🔁 **Auto-refresh auth** — customer_id expires? No problem. openid-based automatic renewal

## Installation

### HACS (Recommended)

1. Add custom repository: `https://github.com/YangXuran/ecowater-china-ha`
2. Search "Ecowater China" in HACS → Install
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration → Ecowater China**

### Manual

```bash
cd /path/to/ha/config/custom_components
git clone https://github.com/YangXuran/ecowater-china-ha.git ecowater_china
# Restart Home Assistant
```

## Configuration

The integration requires three values:

| Field | Required | Description |
|-------|----------|-------------|
| **Phone Number** | Yes | The phone number used to log into the 怡口智控 WeChat mini-program |
| **OpenID** | Yes | Stable WeChat account identifier (capture once, never changes) |
| **Customer ID** | No | Session token — leave blank to auto-fetch, or pre-fill if known |

### 🔑 How to get your `openid` and `customer_id`

The **openid** is a **permanent identifier** bound to your WeChat account. It never changes.
The **customer_id** is a **session token** that expires periodically. But don't worry — the integration will auto-refresh it using your openid.

You only need to capture the openid **once**.

#### Method 1: Charles Proxy (macOS / Windows)

This is the method used to reverse-engineer this integration.

1. **Install Charles Proxy** — https://www.charlesproxy.com/ (free trial works)

2. **Configure SSL Proxying:**
   - Proxy → SSL Proxying Settings → Add
   - Host: `*.chinaecowater.com` Port: `443`

3. **Install Charles root certificate on your phone:**
   - Help → SSL Proxying → Install Charles Root Certificate on a Mobile Device
   - Follow the on-screen instructions (makes your phone trust Charles' certificate)
   - **Important:** On iOS, go to Settings → General → About → Certificate Trust Settings and enable the Charles certificate

4. **Connect your phone to Charles:**
   - Set phone WiFi proxy to your Mac's IP, port `8888`
   - Charles will prompt — click **Allow**

5. **Capture the `openid` (most important!):**
   - Open WeChat → 怡口智控 mini-program → Log in with your phone
   - In Charles, look for requests to `iot2.chinaecowater.com`
   - Find the request to **`POST /api/applets/customer/openid`**
   - In the **Response**, you'll see:
     ```json
     {"openid": "oavuI5KYxxxxxxxxxxxxxxxxxxxxx", "session_key": "..."}
     ```
   - Copy the `openid` value — this is what you'll enter in HA

6. **Capture the `customer_id` (optional — the integration can auto-fetch it):**
   - Find the request to **`POST /api/applets/customer/getCustomer`**
   - In the **Response**, you'll see:
     ```json
     {"data": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "resCode": "0", "resMsg": "ok"}
     ```
   - The `data` field is your current `customer_id`
   - Alternatively, check any authenticated request header: `ewtoken: customer<customer_id>`

> 💡 **You only need the openid.** The integration uses `getCustomer` to fetch a fresh customer_id whenever the old one expires. If you want to pre-fill a customer_id, grab it from the `ewtoken` header of any authenticated request.

```
Capture checklist:
  [✓] POST /api/applets/customer/openid → response → openid (PERMANENT)
  [✓] POST /api/applets/customer/getCustomer → response → data (customer_id, ephemeral)

Hint: in Charles, filter by "openid" to find both requests quickly.
```

---

## API Documentation

**Base URL:** `https://iot2.chinaecowater.com`

**Authentication:** Every request requires header:
```
ewtoken: customer{your_customer_id}
```

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/applets/customer/openid` | POST | WeChat code → openid + session_key |
| `/api/applets/customer/getCustomer` | POST | openid → customer_id (no auth needed!) |
| `/api/applets/cusDev/cusDevListByMC3` | POST | Device real-time data (all `dataXX` fields) |
| `/api/applets/cusDev/cusDevListByMC3New` | POST | Newer device data endpoint (more fields) |
| `/api/app/statiscal/observe/daily` | POST | Today's hourly water usage breakdown |
| `/api/app/statiscal/daily` | POST | Daily water statistics |
| `/api/applets/model/cusLoadConifgsByMac` | GET | Device configuration (hex-encoded) |
| `/api/applets/device/control` | POST | Device control (trigger regeneration) |
| `/api/applets/cusDevFault/list` | POST | Fault/error logs |

### Auth Flow

```
WeChat mini-program wx.login()
  ↓ code
POST /api/applets/customer/openid  {code: ...}
  ↓ openid + session_key
POST /api/applets/customer/getCustomer  {openid: ...}   ← no ewtoken required!
  ↓ customer_id
All subsequent requests: Header ewtoken: customer{customer_id}
```

> **Key insight:** `getCustomer` does NOT require authentication. As long as you have the openid, you can get a fresh customer_id anytime. This is how the auto-refresh works.

### Device State Request

```
POST /api/applets/cusDev/cusDevListByMC3
Headers:
  ewtoken: customer{id}
  Content-Type: application/x-www-form-urlencoded
Body:
  customer={phone}&modelCode=
```

Response returns an array of devices with `data00` through `data75` fields.

---

## Data Field Mapping

### ✅ Confirmed Fields (9 sensors implemented)

| Field | Sensor Name | Unit | How Confirmed | Notes |
|-------|-------------|------|---------------|-------|
| `data0A` | Instant Flow Rate | L/min | Mini-program comparison ✅ | Updates in real-time when water is running |
| `data25` | Regeneration Count | times | Mini-program comparison ✅ | Lifetime count, never resets |
| `data2C` | Available Soft Water | L | Mini-program comparison ✅ | Resets to max after each regeneration |
| `data08` | Regeneration Active | — | Regeneration capture | `0` = idle, `1` = regenerating |
| `data24` | Regeneration Stage | — | Full cycle capture | See [Regeneration Stages](#regeneration-stages) |
| `data22` | Segment Water Use | L | Regeneration tracking | Resets each regeneration cycle |
| `data23` | Segment Count | — | Regeneration tracking | Resets each regeneration cycle |
| `data28` | Cumulative Water Use | L | Continuous tracking | Monotonic increase |
| `data5A` | Inlet Hardness | — | Config comparison | Raw value × 10 = display (17 → 170) |

### 🔒 Hidden Fields (6 sensors — unconfirmed, commented out)

These fields exist in the API response but are **not** exposed as sensors because their values haven't been verified against the mini-program display. You can uncomment them in `custom_components/ecowater_china/sensor.py` if you want to experiment.

| Field | Suspicion | Why Hidden |
|-------|-----------|------------|
| `data00` | Device status (255=normal) | Inference only, not confirmed |
| `data0F` | Online status | Inference only |
| `data13` | Total water use | Unknown unit/accuracy |
| `data29` | Daily avg water use | May be server-side calculation |
| `data2B` | Salt remaining days | Estimate, unverified |
| `data60` | Signal strength (dBm) | Inference only |

### 🔬 Regeneration Stages (`data24`)

| Value | Stage | Duration (typical) | Captured |
|-------|-------|--------------------|----------|
| `0` | Idle | — | ✅ |
| `1` | Backwash (反洗) | ~2-3 min | ❌ (too short to capture) |
| `2` | Brine Draw (吸盐) | ~50 min | ✅ |
| `3` | Slow Rinse (慢洗) | ~3-5 min | ✅ |
| `4` | Fast Rinse (快洗) | ~1-2 min | ✅ |

### ❓ Unconfirmed / Unknown Fields

These fields appeared in the API response but have **not** been mapped to a physical meaning. **Help wanted!**

| Field | Observed Values | Suspicion | How to Confirm |
|-------|-----------------|-----------|----------------|
| `data01` | — | Device subtype? | Compare with mini-program |
| `data02` | — | Firmware version? | Cross-reference with settings |
| `data03`-`data07` | — | Unknown | — |
| `data09` | — | Peak flow rate? | Run water at max flow |
| `data0B`-`data0E` | — | Unknown | — |
| `data10`-`data12` | — | Unknown | — |
| `data14`-`data21` | — | Unknown | — |
| `data26`-`data27` | — | Unknown | — |
| `data2A` | — | Unknown | — |
| `data2D`-`data2F` | — | Unknown | — |
| `data30`-`data59` | — | Unknown; config-related? | Compare with `cusLoadConifgsByMac` |
| `data5B`-`data5F` | — | Unknown | — |
| `data61`-`data75` | — | Unknown | — |

> 💡 **Tip for mapping unknown fields:** Watch the values change while performing specific actions:
> - Run water at a known flow rate → compare with flow meter
> - Trigger regeneration → watch which fields change at each stage
> - Change hardness setting in mini-program → see which hex config field changes

### Configuration API (Hex-Encoded)

Settings are stored as hex strings. Known mappings:

| Config Key | Hex in API | Related dataXX | Display Value | Unit |
|------------|-----------|----------------|---------------|------|
| Hardness (硬度) | `"5A"` → 90 | data5A=17 | 170 | (×10) |
| Regeneration Time (再生时间) | `"51"` → 81 | — | 2:00 AM | (time encode?) |
| Backwash Duration (反冲时间) | `"53"` → 3 | data53=3 | 3 min | minute |
| Fast Rinse Duration (快洗时间) | `"55"` → 1 | data55=1 | 1 min | minute |
| Salt Efficiency Mode (盐效模式) | `"5D"` | — | — | — |
| Low Temp Switch (低温开关) | `"46"` | — | — | — |

> ⚠️ **The time encoding is not yet fully decoded.** Hex `"51"` = decimal 81 somehow maps to 2:00 AM. PR welcome!

---

## Device Control

Trigger an immediate regeneration:

```
POST /api/applets/device/control
Headers:
  ewtoken: customer{id}
  Content-Type: application/x-www-form-urlencoded
Body:
  mac={device_mac}&02=1
```

| Command Code | Action |
|-------------|--------|
| `02=1` | Immediate regeneration |

The integration exposes this as a **Button entity** in HA: `button.yi_kou_v80ecm_yi_kou_li_ji_zai_sheng`

Other command codes are unknown — potentially: vacation mode, bypass valve, manual backwash.

---

## Credentials & Security

- **`openid`** is **permanent** — bound to your WeChat account, never changes. Capture once.
- **`customer_id`** is a **session token** — expires periodically, but the integration auto-refreshes it using your openid via the `getCustomer` endpoint.
- **Phone number** is used as the account identifier in API requests.
- No password or WeChat session is needed after obtaining the openid.

> 🔒 Never commit your `openid`, `customer_id`, or phone number to public repos. The integration uses Home Assistant's config entry system to store these securely.

---

## Contributing

This is a **community reverse-engineering project**. There's still a lot to discover:

### 🔥 High Priority

- [ ] **Map unknown `dataXX` fields** (see table above)
- [ ] **Decode config time format** (hex → HH:MM mapping)
- [ ] **Capture Stage 1 (Backwash)** — need to start Charles before regeneration begins
- [ ] **Add `number` platform** — adjust hardness setting from HA
- [ ] **Multi-device support** (multiple softeners on one account)

### 🧪 Medium Priority

- [ ] Discover other device control command codes
- [ ] Add `cusDevListByMC3New` endpoint support (may expose more fields)
- [ ] Unit confirmation: is hardness in ppm or gpg? (170 ppm ≈ 10 gpg)
- [ ] Fault code mapping (error codes → human-readable descriptions)
- [ ] Add diagnostic sensors (last regeneration time, next scheduled)
- [ ] Verify and enable hidden sensor fields against mini-program

### ✅ Completed

- [x] **Button platform** — trigger regeneration from HA dashboard
- [x] **Auth auto-refresh** — openid-based customer_id renewal

### 📝 How to Contribute

1. Fork the repo
2. Set up Charles Proxy on your Ecowater device
3. Capture data while changing settings / triggering events
4. Document your findings
5. Submit a PR with field mappings or code improvements

### Methodology Reference

The original reverse engineering was done with:

- **Charles Proxy** — SSL man-in-the-middle on macOS
- **iPhone + WeChat** — capturing 怡口智控 mini-program traffic
- **326 requests captured** in `.chlz` format, including a full regeneration cycle
- **Field mapping** by comparing API values side-by-side with mini-program screenshots
- **Auth flow discovery** by analyzing the `openid → getCustomer → ewtoken` chain in Charles session files

---

## Compatibility

- **Home Assistant:** 2024.5+
- **Device tested:** Ecowater V80ECM (modelCode: `000400`)
- **Other models:** Likely compatible if they use the same mini-program (V60, V100, etc.) — please report!

---

## License

MIT

---

## Acknowledgments

- The Home Assistant community for the amazing integration framework
- Charles Proxy for making SSL interception accessible
- Ecowater for building solid hardware (now if only they'd publish an API... 😅)
