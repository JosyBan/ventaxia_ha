class VentAxiaCard extends HTMLElement {
  constructor() {
    super();
    this.userSelectedMode = "normal";
    this.userOptionsSelection = "text";
    this.isCanceled = false;
  }

  setConfig(config) {
    this.config = config;
    this.render();

    if (!this._listenersInitialized) {
      this.setupListeners();
      this._listenersInitialized = true;
    }
  }

  set hass(hass) {
    this._hass = hass;

    const activeEntity = hass.states["sensor.airflow_active"];
    const timerEntity = hass.states["sensor.manual_airflow_timer"];
    // Update the device mode heading from sensor
    const modeEntity = hass.states["sensor.airflow_mode"];

    // You could similarly update other dynamic fields here later
    if (this.currentModeHeading && modeEntity) {
      this.currentModeHeading.textContent = `CURRENT MODE: ${modeEntity.state.toUpperCase()}`;
    }

    if (
      activeEntity &&
      activeEntity.state.toLowerCase() === "true" &&
      timerEntity &&
      !this.isCanceled
    ) {
      const secs = parseInt(timerEntity.state, 10);

      this.showMode(this.userSelectedMode);

      if (!isNaN(secs) && secs > 0 && this.timerDisplay) {
        const mins = Math.floor(secs / 60);
        const s = secs % 60;

        this.timerDisplay.textContent = `${mins}:${s
          .toString()
          .padStart(2, "0")}`;
        this.userOptionsSelection = "countdown"; // lock to countdown
        this.showMode(this.userSelectedMode);
      } else {
        this.showMode(this.userSelectedMode);
      }
    } else {
      // Airflow not active
      this.showMode(this.userSelectedMode);
    }

    // Update Scheduled Mode, update MaintenanceView and PreformanceView dynamically
    this.renderSchedules();
    this.updateSilentHours();
    this.updateSummerBypass();
    this.updateMaintenanceView();
    this.updatePreformanceView();

    if (activeEntity && activeEntity.state.toLowerCase() === "false")
      this.isCanceled = false;
  }

  // The showMode function exactly as in your HTML version
  showMode(mode) {
    this.userSelectedMode = mode;

    // Update active dot
    this.modeDots.forEach((dot) => dot.classList.remove("active"));
    this.querySelector(`.mode-dot[data-mode="${mode}"]`).classList.add(
      "active",
    );

    // Update main circle text
    if (this.mainCircleText)
      this.mainCircleText.textContent = this.userSelectedMode.toUpperCase();

    // Show text view, hide timer/countdown
    this.modeTextView.classList.toggle(
      "hidden",
      this.userOptionsSelection !== "text",
    );
    this.timerOptionsView.classList.toggle(
      "hidden",
      this.userOptionsSelection !== "timer",
    );
    this.countdownView.classList.toggle(
      "hidden",
      this.userOptionsSelection !== "countdown",
    );
    this.modeControlContainer.classList.toggle(
      "pulse",
      this.userOptionsSelection === "countdown",
    );
    this.modeDotsContainer.classList.toggle(
      "hidden",
      this.userOptionsSelection === "countdown",
    );
  }

  createRow(ts, key, list, isTs) {
    if (ts.from && ts.to && ts.mode && ts.days) {
      const li = document.createElement("li");
      if (isTs) li.classList.add("schedule-row");

      if (key === "summer") li.classList.add("summer-bypass-row");

      li.dataset.key = key; // store schedule key
      li.dataset.ts = JSON.stringify(ts); // store full timeslot data for easy access
      // Time range
      const timeSpan = document.createElement("span");
      timeSpan.textContent =
        key === "summer" ? ts.from : `${ts.from} - ${ts.to}`;
      li.appendChild(timeSpan);

      // Days column (new)
      const daysSpan = document.createElement("span");
      daysSpan.textContent = ts.days;
      daysSpan.className = "days";
      li.appendChild(daysSpan);

      // Mode label
      const modeSpan = document.createElement("span");
      modeSpan.textContent = ts.mode;
      modeSpan.className = "mode";
      li.appendChild(modeSpan);

      list.appendChild(li);
    }
  }

  renderSchedules() {
    if (!this._hass) return;

    const scheduleSensor = this._hass.states["sensor.schedules"];
    if (!scheduleSensor?.attributes) return;
    // Clear the current list
    this.scheduleList.innerHTML = "";

    // Loop through each schedule in the sensor attributes
    const schedules = scheduleSensor.attributes;

    // Assuming attributes are like ts1, ts2, ts3, ...
    Object.keys(schedules).forEach((key) => {
      const ts = schedules[key];
      this.createRow(ts, key, this.scheduleList, true);
    });
  }

  updateSilentHours() {
    if (!this._hass) return;

    const silentSensor = this._hass.states["sensor.silent_hours"];
    if (!silentSensor?.attributes) return;

    this.silentRow.innerHTML = ""; // clear existing row(s)

    this.createRow(silentSensor.attributes, "shrs", this.silentRow, false);
  }

  updateSummerBypass() {
    if (!this._hass) return;

    const bypassModeSensor = this._hass.states["sensor.summer_bypass_mode"];
    const summerIndoorTempSensor =
      this._hass.states["sensor.summer_bypass_indoor_temp"];
    const summerOutdoorTempSensor =
      this._hass.states["sensor.summer_bypass_outdoor_temp"];
    const summerBypassAFModeSensor =
      this._hass.states["sensor.summer_bypass_airflow_mode"];

    if (
      !bypassModeSensor?.state ||
      !summerIndoorTempSensor?.state ||
      !summerOutdoorTempSensor?.state ||
      !summerBypassAFModeSensor?.state
    )
      return;

    this.summerBypassUl.innerHTML = ""; // clear existing row(s)
    this.summerAFModeValue.textContent = summerBypassAFModeSensor.state;

    // Create structured data
    const sb = {
      from: `Indoor ${summerIndoorTempSensor.state} °C`, // indoor temperature
      to: " ", // empty as createRow will only reder from for key summer
      mode: `${bypassModeSensor.state}`, // bypass mode
      days: `Indoor ${summerOutdoorTempSensor.state} °C`, // outdoor temperature
      summerIndoorTempRaw: summerIndoorTempSensor.state,
      bypassmodeRaw: bypassModeSensor.state,
      afModeRaw: summerBypassAFModeSensor.state,
      summerOutdoorTempRaw: summerOutdoorTempSensor.state,
    };

    this.createRow(sb, "summer", this.summerBypassUl, false);
  }

  // Called when HA state changes or on first render
  updateMaintenanceView() {
    // Filter months remaining
    const filterValue = this._hass.states["sensor.filter_months_remaining"];
    if (filterValue) {
      this.filterValue.textContent = filterValue.state;
    }

    // Service info
    const serviceValue = this._hass.states["sensor.service_info"];
    if (serviceValue) {
      this.serviceValue.textContent = serviceValue.state;
    }
  }

  // Called when HA state changes or on first render
  updatePreformanceView() {
    // Update the outdoor temperature display
    const outdoor = this._hass.states["sensor.outdoor_temperature"];
    if (outdoor) {
      this.outdoorTempValue.textContent = `${outdoor.state} °C`;
    }

    // Update the indoor temperature display
    const extract = this._hass.states["sensor.indoor_temperature"];
    if (extract) {
      this.extractTempValue.textContent = `${extract.state} °C`;
    }
    // Update the supply temperature display
    const supply = this._hass.states["sensor.supply_air_temperature"];
    if (supply) {
      this.supplyTempValue.textContent = `${supply.state} °C`;
    }
  }

  render() {
    this.innerHTML = `
		<ha-card>
		<style>
			/* General Card */
			.card {
			background: #111827; /* gray-900 */
			border-radius: 1.5rem;
			box-shadow: 0 10px 25px rgba(0,0,0,0.5);
			display: flex;
			flex-direction: column;
			height: 800px;
			overflow: hidden;
			width: 100%;
			}

			/* Header */
			.card-header {
			background: #1f2937;
			padding: 1rem;
			display: flex;
			justify-content: center;
			align-items: center;
			}
			.card-header img { height: 2rem; }

			/* Navigation */
			.card-nav {
			display: flex;
			justify-content: space-around;
			padding: 0.5rem;
			background: #1f2937;
			border-bottom: 1px solid #374151;
			}
			.tab-button {
			flex: 1;
			margin: 0 0.25rem;
			padding: 0.5rem 0;
			border-radius: 9999px;
			font-weight: 500;
			background: #374151;
			color: #d1d5db;
			border: none;
			cursor: pointer;
			}
			.tab-button.active {
			background: #3B82F6;
			color: #fff;
			}
			/* Only apply hover to tabs that are NOT active */
			.tab-button:not(.active):hover {
			background: #4b5563;
			}

			/* Main Content */
			.card-main { flex-grow: 1; padding: 1.5rem; overflow-y: auto; }
			.view { width: 100%; }
			.hidden {
			display: none !important;
			}

			/* Status */
			.mode-heading { font-size: 1.25rem; font-weight: 500; margin-bottom: 2rem; text-align: center; }
			.control-circle {
			position: relative; width: 12rem; height: 12rem; margin: 0 auto 1rem;
			border: 4px solid #4b5563; border-radius: 50%;
			display: flex; align-items: center; justify-content: center;
			cursor: pointer; transition: background-color 0.3s;
			}
			/* Optional: nicer active-border pulse for the control circle when the timer runs */
			.control-circle.pulse {
			border-color: #3B82F6;
			animation: pulse 1.5s ease-in-out infinite;
			}
			@keyframes pulse {
			0%   { box-shadow: 0 0 0 0 rgba(59,130,246,0.4); }
			70%  { box-shadow: 0 0 0 12px rgba(59,130,246,0); }
			100% { box-shadow: 0 0 0 0 rgba(59,130,246,0); }
			}

			.circle-text span { font-size: 1.875rem; font-weight: 600; }
			.timer-options {
			position: absolute;   /* Sit inside the circle */
			top: 0;
			left: 0;
			width: 100%;
			height: 100%;
			display: grid;
			grid-template-columns: repeat(2, 1fr);
			align-items: center;
			justify-items: center;
			gap: 0.5rem;
			padding: 1rem;
			box-sizing: border-box;
			}
			.boost-btn {
			width: 4rem; height: 4rem; background: #2563EB; color: #fff;
			font-weight: 500; border-radius: 50%; border: none;
			cursor: pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.2);
			}
			.boost-btn:hover { background: #1D4ED8; }
			#timer-display { font-size: 2.25rem; font-weight: 200; margin-bottom: 0.5rem; }
			.cancel-btn {
			background: #fff; color: #2563EB; font-weight: 500;
			padding: 0.25rem 1rem; border-radius: 9999px;
			border: none; cursor: pointer;
			}
			.cancel-btn:hover { background: #e5e7eb; }
			.mode-dots { display: flex; justify-content: center; gap: 1rem; }
			.mode-dots.hidden {
				visibility: hidden; /* keeps the space but hides the dots */
			}
			.mode-dot {
			width: 0.75rem; height: 0.75rem; border-radius: 50%;
			background: #4b5563; cursor: pointer;
			}
			.mode-dot.active { background: #3B82F6; }

			/* Scheduled Mode */
			.summer-bypass, .silent-hours, .scheduled-mode {
			background: #1f2937; padding: 1rem; border-radius: 0.5rem;
			margin-top: 2rem; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2);
			}
			.summer-bypass-header, .silent-header, .scheduled-header {
			display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;
			}
			.summer-bypass-title, .silent-title, .scheduled-title { display: flex; align-items: center; font-size: 1.125rem; font-weight: 500; }
			.icon { width: 1.5rem; height: 1.5rem; margin-right: 0.5rem; stroke: #9CA3AF; }
			.new-program {
			display: flex; align-items: center; color: #3B82F6;
			font-weight: 500; background: none; border: none; cursor: pointer;
			}
			.summer-bypass-list, .silent-hours-list, .schedule-list { list-style: none; padding: 0; margin: 0; }
			.summer-bypass-list  li, .silent-hours-list  li, .schedule-list li {
			display: flex; justify-content: space-between;
			border-bottom: 1px solid #374151;
			padding-bottom: 0.5rem; margin-bottom: 0.5rem;
			}
			.schedule-row, .silent-hours-pointer, .summer-bypass-pointer {
				cursor: pointer;
			}
			.summer-bypass-list li:last-child, .silent-hours-list li:last-child, .schedule-list li:last-child { border-bottom: none; margin-bottom: 0; }
			.summer-bypass-list .mode, .silent-hours-list .mode, .schedule-list .mode { color: #60A5FA; font-weight: 500; }
			.summer-bypass-list .unknown, .silent-hours-list .unknown, .schedule-list .unknown { color: #6B7280; font-weight: 300; }

			/* Performance */
			.performance-card {
			position: relative; width: 100%; height: 30rem;
			background: linear-gradient(to bottom, #2563EB, #1E40AF);
			border-radius: 0.75rem;
			box-shadow: 0 8px 16px rgba(0,0,0,0.4);
			display: flex; flex-direction: column;
			justify-content: center; align-items: center;
			}
			.outdoor {
			position: absolute; top: 25%; text-align: center; color: #E5E7EB;
			}
			.outdoor p:first-child { font-size: 1.125rem; }
			.outdoor p:last-child { font-size: 0.875rem; font-weight: 300; text-transform: uppercase; }
			.performance-graph { position: relative; width: 100%; height: 100%; }
			.graph-border {
			position: absolute; bottom: 0; left: 50%; transform: translateX(-50%);
			width: 12rem; height: 12rem; border: 6px solid #fff; border-radius: 0.5rem;
			}
			.graph-bar {position: absolute; bottom: 0; width: 5rem; height: 12rem;background: #fff; border-radius: 0.5rem 0.5rem 0 0;}
			.graph-bar.left { left: 25%; transform: translateX(-50%); }
			.graph-bar.right { right: 25%; transform: translateX(50%); }
			.graph-label {
			position: absolute; bottom: 2rem; text-align: center; color: #fff;
			}
			.graph-label p:first-child { font-size: 1.25rem; font-weight: 500; }
			.graph-label p:last-child {
			font-size: 0.875rem; font-weight: 300;
			text-transform: uppercase; color: #E5E7EB;
			}
			.graph-label.left { left: 25%; transform: translateX(-50%); }
			.graph-label.right { right: 25%; transform: translateX(50%); }

			/* Maintenance */
			.maintenance-card {
			text-align: center;
			background: linear-gradient(to bottom, #2563EB, #1E40AF);
			padding: 2rem; border-radius: 0.75rem;
			box-shadow: 0 8px 16px rgba(0,0,0,0.4);
			margin-bottom: 2rem;
			}
			.maintenance-card .label {
			color: #D1D5DB; text-transform: uppercase;
			font-weight: 300; font-size: 0.875rem; margin-bottom: 0.5rem;
			}
			.maintenance-card .value {
			font-size: 3.75rem; font-weight: 200; margin-bottom: 0.5rem;
			}
			.maintenance-card .sub {
			font-size: 1.125rem; font-weight: 300;
			color: #E5E7EB; text-transform: uppercase;
			}
			/* Scoped CSS using .days-picker-container to avoid global :root */

			.modal {position: fixed;top: 0;left: 0;width: 100%;height: 100%;background: rgba(0,0,0,0.5);display: flex;align-items: flex-start;z-index: 1000;}
			.modal.hidden {display: none;}
			/* Mobile modal: center screen */
			.modal.mobile {width: 100vw;height:100vh;align-items: center;padding: 1rem;box-sizing: border-box;}

			/* Modal content */
			.modal-content {background: #111827;padding: 1.5rem;border-radius: 8px;width: 400px;max-width: 90%;height: 25%;box-shadow: 0 5px 15px rgba(0,0,0,0.3);overflow-y: auto;position: relative;}

			/* Mobile modal content */
			.modal-content.mobile {max-width: 95vw;max-height: 85vh;height: auto;}
			.close-modal {position: absolute;top: 0.5rem;right: 0.5rem;background: none;border: none;font-size: 1.5rem;cursor: pointer;}

			.days-picker-container {--bg:#0f1724;--model-card:#0b1220;--accent:#7c5cff;--muted:#9aa4b2;--size:25px; --width:90%;  }
			.days-picker-container .days-grid{display:grid;grid-template-columns:repeat(8, 1fr);grid-gap:1px;align-items:center;}
			.days-picker-container .day-input{position:absolute;opacity:0;width:1px;height:1px;margin:-1px;padding:0;border:0;clip:rect(0 0 0 0);overflow:hidden;white-space:nowrap;}
			.days-picker-container .day-input:checked + .day{background:linear-gradient(180deg, rgba(124,92,255,0.16), rgba(124,92,255,0.10));color:#fff;border:1px solid rgba(124,92,255,0.35);box-shadow:0 6px 18px rgba(124,92,255,0.08) inset,0 8px 24px rgba(2,6,23,0.6);transform:translateY(-1px);}
			.days-picker-container .day { display:inline-grid; place-items:center; cursor:pointer; border-radius:6px; height:var(--size); width:var(--width); border:1px solid rgba(255,255,255,0.04); background:linear-gradient(180deg, rgba(255,255,255,0.01), rgba(255,255,255,0.005)); user-select:none; font-weight:600; font-size:10px; color:var(--muted); transition:transform .12s ease, box-shadow .12s ease, background .12s ease, color .12s ease; }
			.days-picker-container .day-input:checked + .day { background:#3b82f6; color:#fff; border:1px solid #3b82f6; box-shadow:0 0 4px rgba(59,130,246,0.4) inset; }
			.days-picker-container .btn { display:inline-grid; place-items:center; cursor:pointer; border-radius:6px; height:var(--size); width:var(--width); border:1px solid rgba(255,255,255,0.06); background:#3b82f6; color:#fff; font-weight:600; font-size:10px; transition:background 0.2s ease; }
			.days-picker-container .btn:hover { background:#60a5fa; }
			.modal-actions { display:flex; justify-content:center; gap:0.5rem; padding-top:1rem; }
			.modal-actions .btn { flex:1; margin:0 0.25rem; padding:0.5rem 0; border-radius:9999px; font-weight:500; background:#374151; color:#d1d5db; border:none; cursor:pointer; transition:background 0.2s ease; }
			.modal-actions .btn:hover { background:#4b5563; }
			.modal-actions .btn.delete { background:#b91c1c; color:#fff; }
			.modal-actions .btn.delete:hover { background:#f87171; }
			.modal-actions .btn.save { background:#3b82f6; color:#fff; }
			.modal-actions .btn.save:hover { background:#60a5fa; } input[type="time"] { font-size:16px; padding:5px; border-radius:6px; border:1px solid #ccc; width:100px; cursor:pointer; } input[type="time"]:focus { outline:none; border-color:#3b82f6; box-shadow:0 0 0 2px rgba(59,130,246,0.3); }
			.modal-mode-select {width: 100%;font-size: 16px;padding: 5px;border-radius: 6px;border: 1px solid #ccc;cursor: pointer;height: 28.4px;box-sizing: border-box;}
			.modal-mode-select:focus {outline: none;border-color: #3b82f6;box-shadow: 0 0 0 2px rgba(59,130,246,0.3);}
		</style>

		<div class="card" id="ventaxia-card">
			<!-- Header -->
			<header class="card-header">
			<img src="https://brands.home-assistant.io/ventaxia_ha/dark_logo.png" alt="Vent-Axia Logo">
			</header>

			<!-- Navigation -->
			<nav class="card-nav">
			<button id="status-tab" class="tab-button active">Status</button>
			<button id="performance-tab" class="tab-button">Performance</button>
			<button id="maintenance-tab" class="tab-button">Maintenance</button>
			</nav>

			<!-- Main Content -->
			<main class="card-main">

			<!-- STATUS VIEW -->
			<div id="status-view" class="view">
				<p id="current-mode-heading" class="mode-heading">CURRENT MODE: NORMAL</p>

				<!-- Control Circle -->
				<div id="mode-control-container" class="control-circle">
				<div id="mode-text-view" class="circle-text">
					<span id="main-circle-text">NORMAL</span>
				</div>
				<div id="timer-options-view" class="timer-options hidden">
					<button class="boost-btn" data-minutes="15">15 MIN</button>
					<button class="boost-btn" data-minutes="30">30 MIN</button>
					<button class="boost-btn" data-minutes="45">45 MIN</button>
					<button class="boost-btn" data-minutes="60">60 MIN</button>
				</div>
				<div id="countdown-view" class="countdown hidden">
					<div id="timer-display"></div>
					<button id="cancel-btn" class="cancel-btn">CANCEL</button>
				</div>
				</div>

				<!-- Mode Dots -->
				<div class="mode-dots" id="mode-dots-container">
				<div class="mode-dot active" data-mode="normal"></div>
				<div class="mode-dot" data-mode="boost"></div>
				<div class="mode-dot" data-mode="purge"></div>
				</div>

				<!-- Scheduled Mode -->
				<div class="scheduled-mode">
					<div class="scheduled-header">
						<div class="scheduled-title">
							<svg class="icon" viewBox="0 0 80 80"><path d="m 61,16 h -3 v -6 h -6 v 6 H 28 v -6 h -6 v 6 h -3 c -3.33,0 -6,2.7 -6,6 v 42 c 0,3.33 2.7,6 6,6 h 42 c 3.33,0 6,-2.67 6,-6 V 22 c 0,-3.3 -2.67,-6 -6,-6 m 0,48 H 19 V 34 H 61 V 64 M 61,28 H 19 v -6 h 42 z" style="fill:#ffffff;fill-opacity:1;" /></svg>
							<span>Scheduled mode</span>
						</div>
						<button id="add-schedule-button" class="new-program">
							New program
							<svg class="icon" viewBox="0 0 80  80"><path stroke-linecap="round" stroke-linejoin="round"   d="m 40,32.125 v 15.75 M 47.875,40 h -15.75 m 31.5,0 a 23.625,23.625 0 1 1 -47.25,0 23.625,23.625 0 0 1 47.25,0 z" style="fill:none;stroke:#ffffff;stroke-width:3;stroke-opacity:1;" /></svg>
						</button>
					</div>
					<ul class="schedule-list" id="scheduled-rows">
					</ul>
					<!-- Edit Schedule Modal -->
					<div id="edit-schedule-modal" class="modal hidden">
						<div class="modal-content"  id="edit-schedule-modal-content">
							<button id="close-button" class="close-modal">&times;</button>
							<h2 id="modal-title">Edit Schedule</h2>
							<div class="schedule-details" style="display:grid; grid-template-columns: auto 1fr; row-gap: 0.5rem; column-gap: 1rem; align-items:center;">
								<label class="bypass-group">Bypass Mode</label><select class="bypass-group" id="modal-bypass-mode" ></select>
								<label class="indoor-group">Intdoor Temp</label><input class="indoor-group" id="modal-indoor-temp" >
								<label class="outdoor-group">Outdoor Temp</label><input class="outdoor-group" id="modal-outdoor-temp" >
								<label>Mode</label><select id="modal-mode" class="modal-mode-select"></select>
								<label class="from-group">From</label><input class="from-group" id="modal-from" type="time">
								<label class="to-group">To</label><input class="to-group" id="modal-to" type="time">
								<label class="days-group">Days</label>
								<div class="days-picker-container days-group"><div class="model-card"><form id="daysForm"><div class="days-grid" >
											<button type="button" id="selectAll" class="btn">All</button>
											<input class="day-input" type="checkbox" id="monday" value="monday"><label class="day" for="monday"><div class="abbr">Mon</div></label>
											<input class="day-input" type="checkbox" id="tuesday" value="tuesday"><label class="day" for="tuesday"><div class="abbr">Tue</div></label>
											<input class="day-input" type="checkbox" id="wednesday" value="wednesday"><label class="day" for="wednesday"><div class="abbr">Wed</div></label>
											<input class="day-input" type="checkbox" id="thursday" value="thursday"><label class="day" for="thursday"><div class="abbr">Thu</div></label>
											<input class="day-input" type="checkbox" id="friday" value="friday"><label class="day" for="friday"><div class="abbr">Fri</div></label>
											<input class="day-input" type="checkbox" id="saturday" value="saturday"><label class="day" for="saturday"><div class="abbr">Sat</div></label>
											<input class="day-input" type="checkbox" id="sunday" value="sunday"><label class="day" for="sunday"><div class="abbr">Sun</div></label>
								</div></form></div></div>
							</div>
							<div class="modal-actions">
								<button id="delete-btn" class="btn delete delete-group">Delete</button>
								<button id="save-btn" class="btn save">Save</button>
							</div>
						</div>
					</div>
				</div>
				<div class="silent-hours silent-hours-pointer" id="silent-hours-click">
					<div class="silent-header">
						<div class="silent-title">
							<svg class="icon" viewBox="0 0 80 80" ><path d="m 36,73.333333 c -17,-1.666667 -30,-16 -30,-33 C 6,22 21,7 39.333333,7 c 17.666666,0 32,13.666667 33.333333,31 -1.522143,-0.0348 -5.67673,-0.329967 -6.666667,0 C 64.666666,24.333333 53.333333,13.666667 39.333333,13.666667 c -14.666667,0 -26.666666,11.999999 -26.666666,26.666666 0,13.666667 10.007812,24.973956 23.341146,26.30729 C 35.989236,68.871413 36,71.102463 36,73.333333 Z" style="fill:#ffffff;fill-opacity:1" /><path d="M 37.476793,23.666667 V 41 l -13.333333,8 3.333333,3.333333 15,-8.666667 V 23.666667 h -5" style="fill:#ffffff;fill-opacity:1"/><path d="m 58.767933,45.91612 -3.371867,3.371866 3.371867,3.371867 M 46.296866,44.302786 44.247933,46.35172 51.879,53.982786 h -7.631067 v 9.68 h 6.453333 l 8.066667,8.066667 V 60.871719 l 6.856666,6.8728 c -1.080933,0.8228 -2.290933,1.5004 -3.63,1.8876 v 3.3396 c 2.2264,-0.516266 4.243067,-1.532666 5.937067,-2.920133 l 3.307333,3.2912 2.048934,-2.048933 -14.52,-14.52 m 11.293333,2.048933 c 0,1.516533 -0.322667,2.936267 -0.8712,4.2592 l 2.436133,2.436133 c 1.048667,-2.000533 1.661734,-4.275333 1.661734,-6.695333 0,-6.905066 -4.84,-12.6808 -11.293334,-14.148933 v 3.323467 c 4.662534,1.387466 8.066667,5.7112 8.066667,10.825466 m -4.033333,0 c 0,-2.8556 -1.613334,-5.307866 -4.033334,-6.501733 v 3.565467 l 3.952667,3.952666 c 0.08067,-0.322667 0.08067,-0.6776 0.08067,-1.0164 z"  style="fill:#ffffff;fill-opacity:1" /></svg>
							<span>Silent Hours</span>
						</div>
					</div>
					<ul class="silent-hours-list" id="silent-hours-row">
					</ul>
				</div>
				<div class="summer-bypass summer-bypass-pointer" id="summer-bypass-click">
					<div class="summer-bypass-header">
						<div class="summer-bypass-title">
							<svg class="icon" viewBox="0 0 80 80" ><path  d="M40,47.1c-3.8,0-6.8-3-6.8-6.8c0-3.8,3.1-6.8,6.8-6.8c3.8,0,6.8,3,6.8,6.8C46.8,44,43.8,47.1,40,47.1 M40,31.5 c-4.9,0-8.9,3.9-8.9,8.8c0,4.9,4,8.8,8.9,8.8s8.9-3.9,8.9-8.8C48.9,35.4,44.9,31.5,40,31.5"  style="fill:#ffffff;fill-opacity:1"/><path  d="M40.8,29.7c0,0.4-0.4,0.8-0.8,0.8c-0.4,0-0.8-0.4-0.8-0.8v-4c0-0.4,0.4-0.8,0.8-0.8c0.4,0,0.8,0.4,0.8,0.8V29.7 z" style="fill:#ffffff;fill-opacity:1"/><path  d="M40.8,50.7c0-0.4-0.4-0.8-0.8-0.8c-0.4,0-0.8,0.4-0.8,0.8v4c0,0.4,0.4,0.8,0.8,0.8c0.4,0,0.8-0.4,0.8-0.8V50.7z " style="fill:#ffffff;fill-opacity:1"/><path  d="M50.6,39.5c-0.4,0-0.8,0.4-0.8,0.8c0,0.4,0.4,0.8,0.8,0.8h4c0.4,0,0.8-0.4,0.8-0.8c0-0.4-0.4-0.8-0.8-0.8H50.6z "style="fill:#ffffff;fill-opacity:1"/><path  d="M25.4,39.4c-0.4,0-0.8,0.4-0.8,0.8c0,0.4,0.4,0.8,0.8,0.8h4c0.4,0,0.8-0.4,0.8-0.8c0-0.4-0.4-0.8-0.8-0.8H25.4z " style="fill:#ffffff;fill-opacity:1"/><path  d="M29.7,29.6c-0.3-0.3-0.8-0.3-1.1,0c-0.3,0.3-0.3,0.8,0,1.1l2.9,2.8c0.3,0.3,0.8,0.3,1.1,0 c0.3-0.3,0.3-0.8,0-1.1L29.7,29.6z" style="fill:#ffffff;fill-opacity:1"/><path  d="M50.3,29.6c0.3-0.3,0.8-0.3,1.1,0c0.3,0.3,0.3,0.8,0,1.1l-2.8,2.8c-0.3,0.3-0.8,0.3-1.1,0 c-0.3-0.3-0.3-0.8,0-1.1L50.3,29.6z" style="fill:#ffffff;fill-opacity:1"/><path  d="M29.7,50.8c-0.3,0.3-0.8,0.3-1.1,0c-0.3-0.3-0.3-0.8,0-1.1l2.9-2.8c0.3-0.3,0.8-0.3,1.1,0 c0.3,0.3,0.3,0.8,0,1.1L29.7,50.8z"  style="fill:#ffffff;fill-opacity:1"/>
								<path  d="M50.3,50.8c0.3,0.3,0.8,0.3,1.1,0c0.3-0.3,0.3-0.8,0-1.1l-2.8-2.8c-0.3-0.3-0.8-0.3-1.1,0 c-0.3,0.3-0.3,0.8,0,1.1L50.3,50.8z" style="fill:#ffffff;fill-opacity:1"/><path style="fill:#ffffff;fill-opacity:1"  d="M 15.09375 40.792969 C 14.645705 40.805926 14.216964 41.02194 13.904297 41.394531 C 13.902914 41.396179 13.901769 41.398737 13.900391 41.400391 C 13.809814 41.495398 13.73095 41.603267 13.667969 41.720703 C 13.667689 41.721224 13.668247 41.722135 13.667969 41.722656 L 7.5996094 50.099609 C 7.1996094 50.799609 7.3 51.699219 8 52.199219 C 8.1 52.299219 8.3 52.400391 8.5 52.400391 C 9.1 52.500391 9.6996094 52.300391 10.099609 51.900391 L 14.089844 46.285156 C 16.335608 55.885046 23.831834 63.500216 33.699219 65.900391 C 47.999219 69.400391 62.400781 60.6 65.800781 46.5 C 66.000781 45.7 65.499219 44.899219 64.699219 44.699219 C 63.899219 44.499219 63.100391 45.000781 62.900391 45.800781 C 59.900391 58.300781 47.000391 66.1 34.400391 63 C 25.514866 60.914622 18.766909 53.897595 16.914062 45.152344 L 23.800781 49.300781 C 24.500781 49.800781 25.500391 49.500781 25.900391 48.800781 C 26.400391 48.100781 26.100391 47.099219 25.400391 46.699219 L 15.900391 41 C 15.638614 40.850413 15.362577 40.785194 15.09375 40.792969 z"/><path style="fill:#ffffff;fill-opacity:1" d="M 40.955078 13.746094 C 28.571094 13.260742 17.162109 21.475391 14.099609 33.900391 C 13.899609 34.700391 14.399219 35.499219 15.199219 35.699219 C 15.999219 35.899219 16.9 35.399609 17 34.599609 C 20 22.099609 32.9 14.300391 45.5 17.400391 C 54.258718 19.456008 60.940652 26.303862 62.904297 34.875 L 56.384766 30.947266 C 55.684766 30.547266 54.685156 30.747266 54.285156 31.447266 C 53.785156 32.147266 54.085156 33.148828 54.785156 33.548828 L 63.960938 39.052734 L 63.966797 39.056641 C 64.075036 39.14654 64.19376 39.222124 64.320312 39.279297 C 64.426602 39.367972 64.595909 39.447266 64.685547 39.447266 C 65.28528 39.647177 65.984934 39.449243 66.285156 38.75 C 66.285409 38.749601 66.284904 38.748446 66.285156 38.748047 L 66.287109 38.746094 C 66.287889 38.744857 66.288287 38.743427 66.289062 38.742188 L 72.585938 30.048828 C 72.985938 29.348828 72.885547 28.447266 72.185547 27.947266 C 71.485547 27.547266 70.585938 27.647656 70.085938 28.347656 L 65.929688 34.197266 C 63.707085 24.559562 56.195563 16.906839 46.300781 14.5 C 44.513281 14.0625 42.724219 13.81543 40.955078 13.746094 z"/>
								<path style="fill:#ffffff;fill-opacity:1" d="M8.5,52.4c-0.2,0-0.4-0.1-0.5-0.2c-0.7-0.5-0.8-1.4-0.4-2.1l6.3-8.7c0.5-0.6,1.3-0.8,2-0.4l9.5,5.7 c0.7,0.4,1,1.4,0.5,2.1c-0.4,0.7-1.4,1-2.1,0.5l-8.3-5l-5.4,7.6C9.7,52.3,9.1,52.5,8.5,52.4"/></svg>
							<span>Summer Bypass</span>
						</div>
						<div class="new-program" id="bypass_af_mode">
							Night Time Fresh
						</div>
					</div>
					<ul class="summer-bypass-list" id="summer-bypass-ul" >
						<li><span>Indoor 19.0 °C</span><span>Outdoor 19.0 °C</span><span  class="mode">Normal</span></li>
						</ul>
				</div>

			</div>

			<!-- PERFORMANCE VIEW -->
			<div id="performance-view" class="view hidden">
				<div class="performance-card">

				<svg version="1.1" id="svg1" width="100%" height="100%" viewBox="0 0 1077 1213" sodipodi:docname="ssvent.svg" inkscape:version="1.4.2 (f4327f4, 2025-05-13)" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg">
				<defs id="defs1">
				<linearGradient id="linearGradient3" inkscape:collect="always"><stop style="stop-color:#2561E8;stop-opacity:1;" offset="0" id="stop3" /><stop style="stop-color:#2151CD;stop-opacity:1;" offset="0.5" id="stop5" /><stop style="stop-color:#1E40AF;stop-opacity:1;" offset="1" id="stop4" /></linearGradient>
				<linearGradient inkscape:collect="always" xlink:href="#linearGradient3" id="linearGradient4" x1="444.52606" y1="69.267448" x2="444.52606" y2="1146.1774" gradientUnits="userSpaceOnUse" gradientTransform="translate(93.338095,-1.4142136)" />
				</defs>
				<sodipodi:namedview id="namedview1" pagecolor="#ffffff" bordercolor="#000000" borderopacity="0.25" inkscape:showpageshadow="2" inkscape:pageopacity="0.0" inkscape:pagecheckerboard="0" inkscape:deskcolor="#d1d1d1" inkscape:zoom="0.48845837" inkscape:cx="816.85569" inkscape:cy="654.09873" inkscape:window-width="2560" inkscape:window-height="1387" inkscape:window-x="-8" inkscape:window-y="-8" inkscape:window-maximized="1" inkscape:current-layer="g1" showgrid="false" showguides="true">
				<inkscape:grid id="grid1" units="px" originx="0" originy="0" spacingx="1" spacingy="1" empcolor="#0099e5" empopacity="0.30196078" color="#0099e5" opacity="0.14901961" empspacing="5" enabled="true" visible="false" />
				</sodipodi:namedview><g inkscape:groupmode="layer" inkscape:label="Image" id="g1"><path style="display:inline;fill:url(#linearGradient4);fill-rule:evenodd;stroke:none;stroke-width:0.00924255" d="m 1076.9909,0.00727413 0.01,1213.00082587 -1076.96484257,-0 L 0.03443235,0.00811697 Z" id="path26-2-2-6-1" sodipodi:nodetypes="ccccc" /><path style="fill:#2A6CE1;fill-opacity:1;fill-rule:evenodd;stroke:none;stroke-width:0.0185383" d="m 857.75637,250.35751 c 30.26962,-0.32575 57.7666,38.11777 58.85442,55.7761 19.8579,-8.17922 35.1499,9.44131 37.13079,21.00434 19.74612,-12.8608 43.73879,10.67628 32.93045,26.54134 H 737.96368 c -8.66312,-17.77921 12.30568,-58.96307 48.1141,-44.45023 7.87075,-41.15627 30.2771,-60.14107 71.67859,-58.87155 z" id="path26" sodipodi:nodetypes="ccccccc" /><path style="fill:#2A6CE1;fill-opacity:1;fill-rule:evenodd;stroke:none;stroke-width:0.0147925" d="m 186.87073,265.66975 c 24.03215,-0.26124 45.86299,30.56933 46.72665,44.73079 15.7659,-6.5595 27.90677,7.57164 29.47947,16.84486 15.67715,-10.31399 34.72582,8.56206 26.14465,21.28537 H 91.763001 c -6.877962,-14.2584 9.769919,-47.28664 38.199519,-35.64777 6.24887,-33.00612 24.03808,-48.23136 56.90821,-47.21325 z" id="path26-2" sodipodi:nodetypes="ccccccc" />
				<path style="fill:#2A6CE1;fill-opacity:1;fill-rule:evenodd;stroke:none;stroke-width:0.00924255" d="m 351.31492,237.44672 c 14.61478,-0.16769 27.89086,19.62409 28.41608,28.71508 9.58779,-4.21089 16.97107,4.86065 17.92748,10.81363 9.53382,-6.62111 21.11797,5.49644 15.89947,13.6642 H 293.47663 c -4.18272,-9.15322 5.94143,-30.35581 23.23045,-22.8842 3.80015,-21.18839 14.61838,-30.96229 34.60784,-30.30871 z" id="path26-2-2" sodipodi:nodetypes="ccccccc" />
				<path style="display:inline;fill:#2048BE;fill-opacity:1;fill-rule:evenodd;stroke:none;stroke-width:0.00925853" d="m 540.95,362.35778 c 14.66537,-0.16769 500.0203,254.63706 500.0203,254.63706 L 1042.3,1212.9894 41.253312,1213.3603 40.943209,616.92916 c 0,0 479.948121,-255.22536 500.006791,-254.57178 z" id="path26-2-2-6" sodipodi:nodetypes="ccccccc" />
				<text id="outdoor-temp-text" x="539.07599" y="187.70222" font-size="44.896px" text-anchor="middle" fill="#ffffff" style="stroke-width:2.49422">20.6 °C</text><text x="540" y="232.59816" font-size="23px" text-anchor="middle" fill="#dddddd" id="text5" style="stroke-width:2.49422">OUTDOOR</text>
				<text id="extract-temp-text" x="64.103325" y="783.2038" font-size="44.896px" text-anchor="start" fill="#ffffff"  style="stroke-width:2.49422">22.7 °C</text><text x="84" y="826" font-size="23px" text-anchor="start" fill="#dddddd" id="text7" style="stroke-width:2.49422">EXTRACT</text>
				<text id="supply-temp-text" x="1018.7986" y="783.2038" font-size="44.896px" text-anchor="end" fill="#ffffff"  style="stroke-width:2.49422">22.0 °C</text><text x="990" y="826" font-size="23px" text-anchor="end" fill="#dddddd" id="text9" style="stroke-width:2.49422">SUPPLY</text>
				<g id="circle-dots-8" transform="matrix(1.5980219,0,0,1.5980219,540.03936,792.85042)">
				<!-- 24 dots, 15° apart --><!-- radius = 100 --><!-- delay increments by 0.1s --><!-- pulse both size and opacity --><!-- You can tweak r="4" (base) and scale it to r="7" in animation -->
				<g id="g1-8"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle1-2"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0s" /></circle></g>
				<g transform="rotate(15)" id="g2-4"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle2"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.1s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.1s" /></circle></g>
				<g transform="rotate(30)" id="g3-5"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle3-5"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.2s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.2s" /></circle></g>
				<g transform="rotate(45)" id="g4-1"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle4-7"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.3s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.3s" /></circle></g>
				<g transform="rotate(60)" id="g5-1"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle5-1"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.4s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.4s" /></circle></g>
				<g transform="rotate(75)" id="g6-5"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle6-2"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.5s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.5s" /></circle></g>
				<g transform="rotate(90)" id="g7-7"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle7-6"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.6s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.6s" /></circle></g>
				<g transform="rotate(105)" id="g8-1"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle8-4"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.7s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.7s" /></circle></g>
				<g transform="rotate(120)" id="g9-2"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle9-3"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.8s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.8s" /></circle></g>
				<g transform="rotate(135)" id="g10-2"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle10-2"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.9s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.9s" /></circle></g>
				<g transform="rotate(150)" id="g11-1"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle11-6"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1s" /></circle></g>
				<g transform="rotate(165)" id="g12-8"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle12-5"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.1s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.1s" /></circle></g>
				<g transform="scale(-1)" id="g13-7">
				<circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle13-6"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.2s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.2s" /></circle></g>
				<g transform="rotate(-165)" id="g14-1"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle14-8"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.3s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.3s" /></circle></g>
				<g transform="rotate(-150)" id="g15-9"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle15-2"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.4s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.4s" /></circle></g>
				<g transform="rotate(-135)" id="g16-7"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle16-9"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.5s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.5s" /></circle></g>
				<g transform="rotate(-120)" id="g17-5"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle17-4"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.6s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.6s" /></circle></g>
				<g transform="rotate(-105)" id="g18-3"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle18-1"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.7s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.7s" /></circle></g>
				<g transform="rotate(-90)" id="g19-2"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle19-3"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.8s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.8s" /></circle></g>
				<g transform="rotate(-75)" id="g20-3"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle20-4"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.9s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.9s" /></circle></g>
				<g transform="rotate(-60)" id="g21-1"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle21-1"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="2s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2s" /></circle></g>
				<g transform="rotate(-45)" id="g22-3"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle22-8"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="2.1s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2.1s" /></circle></g>
				<g transform="rotate(-30)" id="g23-7"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle23-4"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="2.2s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2.2s" /></circle></g>
				<g transform="rotate(-15)" id="g24-2"><circle r="4" cx="0" cy="-100" fill="#3787F5" id="circle24-7"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="2.3s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2.3s" /></circle></g></g>
				<g transform="matrix(0,1.2762816,-1.2762815,0,600.47283,258.73667)" id="g20">
				<!-- Left half, gradually growing to r=4 at midpoint -->
				<circle cx="0" cy="0" r="1.5599999" fill="#3787F5" id="circle1-8"><animate attributeName="r" values="1.56;1.66;1.56" dur="2.5s" repeatCount="indefinite" begin="0s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0s" /></circle>
				<circle cx="20" cy="0" r="1.73" fill="#3787F5" id="circle2-5"><animate attributeName="r" values="1.73;1.83;1.73" dur="2.5s" repeatCount="indefinite" begin="0.125s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.125s" /></circle>
				<circle cx="40" cy="0" r="1.92" fill="#3787F5" id="circle3-7"><animate attributeName="r" values="1.92;2.02;1.92" dur="2.5s" repeatCount="indefinite" begin="0.25s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.25s" /></circle>
				<circle cx="60" cy="0" r="2.1300001" fill="#3787F5" id="circle4-6"><animate attributeName="r" values="2.13;2.23;2.13" dur="2.5s" repeatCount="indefinite" begin="0.375s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.375s" /></circle>
				<circle cx="80" cy="0" r="2.3699999" fill="#3787F5" id="circle5-18"><animate attributeName="r" values="2.37;2.47;2.37" dur="2.5s" repeatCount="indefinite" begin="0.5s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.5s" /></circle>
				<circle cx="100" cy="0" r="2.6300001" fill="#3787F5" id="circle6-9"><animate attributeName="r" values="2.63;2.73;2.63" dur="2.5s" repeatCount="indefinite" begin="0.625s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.625s" /></circle>
				<circle cx="120" cy="0" r="2.9200001" fill="#3787F5" id="circle7-2"><animate attributeName="r" values="2.92;3.02;2.92" dur="2.5s" repeatCount="indefinite" begin="0.75s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.75s" /></circle>
				<circle cx="140" cy="0" r="3.24" fill="#3787F5" id="circle8-7"><animate attributeName="r" values="3.24;3.34;3.24" dur="2.5s" repeatCount="indefinite" begin="0.875s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.875s" /></circle>
				<circle cx="160" cy="0" r="3.5999999" fill="#3787F5" id="circle9-9"><animate attributeName="r" values="3.6;3.7;3.6" dur="2.5s" repeatCount="indefinite" begin="1s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1s" /></circle>
				<circle cx="180" cy="0" r="4" fill="#3787F5" id="circle10-5"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.125s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.125s" /></circle>
				<!-- Right half, stays at r=4 -->
				<circle cx="200" cy="0" r="4" fill="#3787F5" id="circle11-4"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.25s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.25s" /></circle>
				<circle cx="220" cy="0" r="4" fill="#3787F5" id="circle12-3"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.375s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.375s" /></circle>
				<circle cx="240" cy="0" r="4" fill="#3787F5" id="circle13-1"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.5s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.5s" /></circle>
				<circle cx="260" cy="0" r="4" fill="#3787F5" id="circle14-2"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.625s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.625s" /></circle>
				<circle cx="280" cy="0" r="4" fill="#3787F5" id="circle15-3"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.75s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.75s" /></circle>
				</g><g transform="matrix(0,-1.2762816,1.2762815,0,472.65428,743.8308)" id="g20-9">
				<!-- Left half, normal size, pulse +0.1 -->
				<circle cx="100" cy="0" r="4" fill="#3787F5" id="circle6-5"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.625s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.625s" /></circle>
				<circle cx="120" cy="0" r="4" fill="#3787F5" id="circle7-5"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.75s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.75s" /></circle>
				<circle cx="140" cy="0" r="4" fill="#3787F5" id="circle8-1"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="0.875s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.875s" /></circle>
				<circle cx="160" cy="0" r="4" fill="#3787F5" id="circle9-7"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1s" /></circle>
				<circle cx="180" cy="0" r="4" fill="#3787F5" id="circle10-1"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.125s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.125s" /></circle>
				<!-- Right half, gradually smaller, pulse = radius + 0.1 -->
				<circle cx="200" cy="0" r="4" fill="#3787F5" id="circle11-1-4"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.25s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.25s" /></circle>
				<circle cx="220" cy="0" r="3.5999999" fill="#3787F5" id="circle12-5-1"><animate attributeName="r" values="3.6;3.7;3.6" dur="2.5s" repeatCount="indefinite" begin="1.375s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.375s" /></circle>
				<circle cx="240" cy="0" r="3.24" fill="#3787F5" id="circle13-2"><animate attributeName="r" values="3.24;3.34;3.24" dur="2.5s" repeatCount="indefinite" begin="1.5s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.5s" /></circle>
				<circle cx="260" cy="0" r="2.9200001" fill="#3787F5" id="circle14-7"><animate attributeName="r" values="2.92;3.02;2.92" dur="2.5s" repeatCount="indefinite" begin="1.625s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.625s" /></circle>
				<circle cx="280" cy="0" r="2.6300001" fill="#3787F5" id="circle15-6"><animate attributeName="r" values="2.63;2.73;2.63" dur="2.5s" repeatCount="indefinite" begin="1.75s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.75s" /></circle>
				<circle cx="300" cy="0" r="2.3699999" fill="#3787F5" id="circle16-1"><animate attributeName="r" values="2.37;2.47;2.37" dur="2.5s" repeatCount="indefinite" begin="1.875s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.875s" /></circle>
				<circle cx="320" cy="0" r="2.1300001" fill="#3787F5" id="circle17-4-1"><animate attributeName="r" values="2.13;2.23;2.13" dur="2.5s" repeatCount="indefinite" begin="2s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2s" /></circle>
				<circle cx="340" cy="0" r="1.92" fill="#3787F5" id="circle18-2"><animate attributeName="r" values="1.92;2.02;1.92" dur="2.5s" repeatCount="indefinite" begin="2.125s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2.125s" /></circle>
				<circle cx="360" cy="0" r="1.73" fill="#3787F5" id="circle19-3-3"><animate attributeName="r" values="1.73;1.83;1.73" dur="2.5s" repeatCount="indefinite" begin="2.25s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2.25s" /></circle>
				<circle cx="380" cy="0" r="1.5599999" fill="#3787F5" id="circle20-2"><animate attributeName="r" values="1.56;1.66;1.56" dur="2.5s" repeatCount="indefinite" begin="2.375s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2.375s" /></circle>
				</g><g transform="matrix(1.2762816,0,0,1.2762815,127.19957,792.65328)" id="g20-7">
				<!-- Left half, gradually growing to r=4 at midpoint -->
				<circle cx="0" cy="0" r="1.5599999" fill="#3787F5" id="circle1-8-7"><animate attributeName="r" values="1.56;1.66;1.56" dur="2.5s" repeatCount="indefinite" begin="0s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0s" /></circle>
				<circle cx="20" cy="0" r="1.73" fill="#3787F5" id="circle2-5-9"><animate attributeName="r" values="1.73;1.83;1.73" dur="2.5s" repeatCount="indefinite" begin="0.125s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.125s" /></circle>
				<circle cx="40" cy="0" r="1.92" fill="#3787F5" id="circle3-7-3"><animate attributeName="r" values="1.92;2.02;1.92" dur="2.5s" repeatCount="indefinite" begin="0.25s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.25s" /></circle>
				<circle cx="60" cy="0" r="2.1300001" fill="#3787F5" id="circle4-6-1"><animate attributeName="r" values="2.13;2.23;2.13" dur="2.5s" repeatCount="indefinite" begin="0.375s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.375s" /></circle>
				<circle cx="80" cy="0" r="2.3699999" fill="#3787F5" id="circle5-18-9"><animate attributeName="r" values="2.37;2.47;2.37" dur="2.5s" repeatCount="indefinite" begin="0.5s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.5s" /></circle>
				<circle cx="100" cy="0" r="2.6300001" fill="#3787F5" id="circle6-9-8"><animate attributeName="r" values="2.63;2.73;2.63" dur="2.5s" repeatCount="indefinite" begin="0.625s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.625s" /></circle>
				<circle cx="120" cy="0" r="2.9200001" fill="#3787F5" id="circle7-2-6"><animate attributeName="r" values="2.92;3.02;2.92" dur="2.5s" repeatCount="indefinite" begin="0.75s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.75s" /></circle>
				<circle cx="140" cy="0" r="3.24" fill="#3787F5" id="circle8-7-5"><animate attributeName="r" values="3.24;3.34;3.24" dur="2.5s" repeatCount="indefinite" begin="0.875s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="0.875s" /></circle>
				<circle cx="160" cy="0" r="3.5999999" fill="#3787F5" id="circle9-9-0"><animate attributeName="r" values="3.6;3.7;3.6" dur="2.5s" repeatCount="indefinite" begin="1s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1s" /></circle>
				<circle cx="180" cy="0" r="4" fill="#3787F5" id="circle10-5-2"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.125s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.125s" /></circle>
				<!-- Right half, stays at r=4 -->
				</g><g transform="matrix(1.2762816,0,0,1.2762815,466.22807,792.88137)" id="g20-9-0">
				<!-- Left half, normal size, pulse +0.1 -->
				<!-- Right half, gradually smaller, pulse = radius + 0.1 -->
				<circle cx="200" cy="0" r="4" fill="#3787F5" id="circle11-1-4-0"><animate attributeName="r" values="4;4.1;4" dur="2.5s" repeatCount="indefinite" begin="1.25s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.25s" /></circle>
				<circle cx="220" cy="0" r="3.5999999" fill="#3787F5" id="circle12-5-1-6"><animate attributeName="r" values="3.6;3.7;3.6" dur="2.5s" repeatCount="indefinite" begin="1.375s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.375s" /></circle>
				<circle cx="240" cy="0" r="3.24" fill="#3787F5" id="circle13-2-6"><animate attributeName="r" values="3.24;3.34;3.24" dur="2.5s" repeatCount="indefinite" begin="1.5s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.5s" /></circle>
				<circle cx="260" cy="0" r="2.9200001" fill="#3787F5" id="circle14-7-1"><animate attributeName="r" values="2.92;3.02;2.92" dur="2.5s" repeatCount="indefinite" begin="1.625s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.625s" /></circle>
				<circle cx="280" cy="0" r="2.6300001" fill="#3787F5" id="circle15-6-8"><animate attributeName="r" values="2.63;2.73;2.63" dur="2.5s" repeatCount="indefinite" begin="1.75s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.75s" /></circle>
				<circle cx="300" cy="0" r="2.3699999" fill="#3787F5" id="circle16-1-4"><animate attributeName="r" values="2.37;2.47;2.37" dur="2.5s" repeatCount="indefinite" begin="1.875s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="1.875s" /></circle>
				<circle cx="320" cy="0" r="2.1300001" fill="#3787F5" id="circle17-4-1-9"><animate attributeName="r" values="2.13;2.23;2.13" dur="2.5s" repeatCount="indefinite" begin="2s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2s" /></circle>
				<circle cx="340" cy="0" r="1.92" fill="#3787F5" id="circle18-2-6"><animate attributeName="r" values="1.92;2.02;1.92" dur="2.5s" repeatCount="indefinite" begin="2.125s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2.125s" /></circle>
				<circle cx="360" cy="0" r="1.73" fill="#3787F5" id="circle19-3-3-3"><animate attributeName="r" values="1.73;1.83;1.73" dur="2.5s" repeatCount="indefinite" begin="2.25s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2.25s" /></circle>
				<circle cx="380" cy="0" r="1.5599999" fill="#3787F5" id="circle20-2-7"><animate attributeName="r" values="1.56;1.66;1.56" dur="2.5s" repeatCount="indefinite" begin="2.375s" /><animate attributeName="fill" values="#3787F5;white;#3787F5" dur="2.5s" repeatCount="indefinite" begin="2.375s" /></circle></g></g>
				</svg>

				</div>
			</div>

			<!-- MAINTENANCE VIEW -->
			<div id="maintenance-view" class="view hidden">
				<div class="maintenance-card">
				<p class="label">Filter</p>
				<p id="filter-value" class="value">--</p>
				<p class="sub">Months left</p>
				</div>
				<div class="maintenance-card">
				<p class="label">Service</p>
				<p id="service-value" class="value">--</p>
				<p class="sub">Months</p>
				</div>
			</div>
			</main>
		</div>
		</ha-card>
	`;
  }

  setupListeners() {
    const navButtons = this.querySelectorAll(".tab-button");
    const contentViews = this.querySelectorAll(".view");
    const modal = this.querySelector("#edit-schedule-modal");
    const modalContent = this.querySelector("#edit-schedule-modal-content");
    const selectMode = this.querySelector("#modal-mode");
    const selectBypassMode = this.querySelector("#modal-bypass-mode");
    const allBtn = modal.querySelector("#selectAll");
    const deleteBtn = this.querySelector("#delete-btn");
    const saveBtn = this.querySelector("#save-btn");
    const inputs = Array.from(modal.querySelectorAll(".day-input"));
    const mainCard = this.querySelector("#ventaxia-card");
    const closeBtn = this.querySelector("#close-button");
    const modalTitle = this.querySelector("#modal-title");
    const addScheduleBtn = this.querySelector("#add-schedule-button");

    this.summerBypass = this.querySelector("#summer-bypass-click");
    this.silentHoursClick = this.querySelector("#silent-hours-click");
    this.currentModeHeading = this.querySelector("#current-mode-heading");
    this.mainCircleText = this.querySelector("#main-circle-text");
    this.modeTextView = this.querySelector("#mode-text-view");
    this.timerOptionsView = this.querySelector("#timer-options-view");
    this.countdownView = this.querySelector("#countdown-view");
    this.modeDots = this.querySelectorAll(".mode-dot");
    this.modeControlContainer = this.querySelector("#mode-control-container");
    const boostButtons = this.querySelectorAll(".boost-btn");
    this.timerDisplay = this.querySelector("#timer-display");
    const cancelBtn = this.querySelector("#cancel-btn");
    this.modeDotsContainer = this.querySelector("#mode-dots-container");
    this.scheduleList = this.querySelector("#scheduled-rows");
    this.silentRow = this.querySelector("#silent-hours-row");
    this.summerBypassUl = this.querySelector("#summer-bypass-ul");
    this.filterValue = this.querySelector("#filter-value");
    this.serviceValue = this.querySelector("#service-value");
    this.outdoorTempValue = this.querySelector("#outdoor-temp-text");
    this.extractTempValue = this.querySelector("#extract-temp-text");
    this.supplyTempValue = this.querySelector("#supply-temp-text");
    this.summerAFModeValue = this.querySelector("#bypass_af_mode");

    this.userSelectedMode = "normal";
    // Set days checkboxes
    this.dayMap = {
      Mon: "monday",
      Tue: "tuesday",
      Wed: "wednesday",
      Thu: "thursday",
      Fri: "friday",
      Sat: "saturday",
      Sun: "sunday",
    };

    selectMode.innerHTML = "";
    selectBypassMode.innerHTML = "";

    // Add options
    ["Off", "Low", "Normal", "Boost", "Purge"].forEach((opt) => {
      const option = document.createElement("option");
      option.value = opt;
      option.textContent = opt;
      selectMode.appendChild(option);
    });

    // Add options
    ["Off", "Normal", "Evening fresh", "Night fresh"].forEach((opt) => {
      const option = document.createElement("option");
      option.value = opt;
      option.textContent = opt;
      selectBypassMode.appendChild(option);
    });

    const reverseDayMap = Object.fromEntries(
      Object.entries(this.dayMap).map(([short, full]) => [full, short]),
    );

    // Unified function to populate modal
    const showModal = (data, key) => {
      if (!data) return;

      const isMobile = window.matchMedia("(max-width: 768px)").matches;

      console.log("isMobile:", isMobile);
      // Show modal
      modal.classList.remove("hidden");

      if (!isMobile) {
        modal.classList.remove("mobile");
        modalContent.classList.remove("mobile");

        const rect = mainCard.getBoundingClientRect();
        modal.style.display = "block";

        modalContent.style.top = `${
          rect.top + rect.height / 2 - modalContent.offsetHeight / 2
        }px`;
        modalContent.style.left = `${
          rect.left + rect.width / 2 - modalContent.offsetWidth / 2
        }px`;
      } else {
        modal.classList.add("mobile");
        modalContent.classList.add("mobile");
        modal.style.display = "flex";
        modalContent.style.position = "relative";
        modalContent.style.top = "auto";
        modalContent.style.left = "auto";
      }

      // Fill inputs
      selectMode.value = key === "summer" ? data.afModeRaw : data.mode;

      const showFields = (...selectors) => {
        selectors.forEach((sel) => {
          const nodes = modal.querySelectorAll(sel);
          modal
            .querySelectorAll(sel)
            .forEach((el) => el.classList.remove("hidden"));
        });
      };

      const hideFields = (...selectors) => {
        selectors.forEach((sel) => {
          modal
            .querySelectorAll(sel)
            .forEach((el) => el.classList.add("hidden"));
        });
      };
      modal.dataset.key = key;

      if (key === "summer") {
        selectBypassMode.value = data.bypassmodeRaw;
        modal.querySelector("#modal-indoor-temp").value =
          data.summerIndoorTempRaw;
        modal.querySelector("#modal-outdoor-temp").value =
          data.summerOutdoorTempRaw;
        modalTitle.textContent = "Edit Summer Bypass";
        showFields(".indoor-group", ".outdoor-group", ".bypass-group");
        hideFields(".from-group", ".to-group", ".days-group", ".delete-group");
      } else {
        modal.querySelector("#modal-from").value = data.from;
        modal.querySelector("#modal-to").value = data.to;
        modalTitle.textContent =
          key === "shrs" ? "Edit Silent Hours" : "Edit Schedule";
        showFields(
          ".from-group",
          ".to-group",
          ".days-group",
          ...(key !== "shrs" ? [".delete-group"] : []),
        );
        hideFields(
          ".indoor-group",
          ".outdoor-group",
          ".bypass-group",
          ...(key === "shrs" ? [".delete-group"] : []),
        );

        let selectedDays;
        if (data.days.toLowerCase() === "every day") {
          selectedDays = Object.values(this.dayMap);
        } else {
          selectedDays = data.days
            .split(",")
            .map((d) => this.dayMap[d.trim()] || d.trim().toLowerCase());
        }

        inputs.forEach((input) => {
          input.checked = selectedDays.includes(input.value);
        });
      }
    };

    // Show timer option buttons instead of mode text
    const showTimerOptions = () => {
      this.modeTextView.classList.add("hidden");
      this.timerOptionsView.classList.remove("hidden");
      this.countdownView.classList.add("hidden");
      this.userOptionsSelection = "timer";
    };

    // Show countdown view
    const showCountdown = () => {
      this.modeTextView.classList.add("hidden");
      this.timerOptionsView.classList.add("hidden");
      this.countdownView.classList.remove("hidden");
      this.userOptionsSelection = "countdown";
    };

    // tab switching
    navButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        navButtons.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");

        const viewId = btn.id.replace("-tab", "");
        contentViews.forEach((v) => v.classList.add("hidden"));
        this.querySelector(`#${viewId}-view`).classList.remove("hidden");
      });
    });

    // Mode dots — now exactly like HTML, calls showMode()
    this.modeDots.forEach((dot) => {
      dot.addEventListener("click", () => {
        const mode = dot.dataset.mode;
        this.userOptionsSelection = "text";
        this.showMode(mode);
      });
    });

    // Control circle click → show timer options
    this.modeControlContainer.addEventListener("click", () => {
      if (this.isCanceled) return;
      showTimerOptions();
    });

    // Boost buttons
    boostButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const minutes = btn.dataset.minutes;
        // Call HA service
        if (this._hass) {
          this._hass.callService("ventaxia_ha", "set_airflow_mode", {
            mode: this.userSelectedMode,
            duration: minutes,
          });
        }
        // Switch UI to countdown view
        showCountdown();
      });
    });

    // Cancel button
    cancelBtn.addEventListener("click", () => {
      // Optional: call a cancel service if available
      // Initialize mode to normal
      this.isCanceled = true;
      this.userOptionsSelection = "text";
      this.showMode("normal");
      if (this._hass) {
        this._hass.callService("ventaxia_ha", "set_airflow_mode", {
          mode: "reset",
          duration: "0",
        });
      }
    });

    // --- Scheduled Mode click ---
    this.scheduleList.addEventListener("click", (event) => {
      const row = event.target.closest("li.schedule-row");
      if (!row) return;

      const key = row.dataset.key;
      const schedules = this._hass.states["sensor.schedules"].attributes;
      const ts = schedules[key];
      showModal(ts, key);
    });

    addScheduleBtn.addEventListener("click", () => {
      const schedules = this._hass.states["sensor.schedules"]?.attributes || {};

      // Get numeric parts of existing ts keys
      const existingNumbers = Object.keys(schedules)
        .filter((k) => k.startsWith("ts"))
        .map((k) => parseInt(k.replace("ts", ""), 10))
        .filter((n) => !isNaN(n));

      // Determine next number
      const nextNumber = existingNumbers.length
        ? Math.max(...existingNumbers) + 1
        : 1;
      const newKey = `ts${nextNumber}`;

      // Prepare empty/default payload for new schedule
      const payload = {
        name: newKey,
        from: "00:00", // default start time
        to: "00:00", // default end time
        days: "Every day", // default days
        mode: "Normal", // default mode
      };

      // Show modal pre-filled with defaults for the new schedule
      showModal(payload, newKey);
    });

    // --- Silent Hours click ---
    this.silentHoursClick.addEventListener("click", () => {
      const sh = this._hass.states["sensor.silent_hours"].attributes;
      showModal(sh, "shrs");
    });

    // --- Summer Bypass click ---
    this.summerBypass.addEventListener("click", (event) => {
      const row = event.target.closest("li.summer-bypass-row");
      if (!row) return;
      const sb = JSON.parse(row.dataset.ts);

      console.log("Summer Bypass clicked - ", sb);

      showModal(sb, "summer");
    });

    allBtn.addEventListener("click", () => {
      const allSelected = inputs.every((i) => i.checked);
      inputs.forEach((i) => (i.checked = !allSelected));
    });
    deleteBtn.addEventListener("click", () => {
      const key = modal.dataset.key;
      if (!key || key === "summer" || key === "shrs") {
        console.warn("Cannot delete this type of schedule");
        return;
      }

      // Build payload with schema-required fields + extra delete flag
      const payload = {
        name: key,
        from: "00:00", // dummy valid value to pass schema
        to: "00:00", // dummy valid value to pass schema
        days: "Every day", // dummy valid value to pass schema
        mode: "Normal", // any valid mode to satisfy schema
        delete: true, // extra key for backend logic
      };
      console.log("Deleting schedule:", payload);
      this._hass.callService(
        "ventaxia_ha",
        "update_schedule_or_silent_hours",
        payload,
      );

      // Hide the modal after deleting
      modal.classList.add("hidden");
    });

    saveBtn.addEventListener("click", () => {
      const key = modal.dataset.key;

      let payload = null;

      if (key === "summer") {
        const indoorTemp = modal.querySelector("#modal-indoor-temp").value;
        const outdoorTemp = modal.querySelector("#modal-outdoor-temp").value;

        const MODES = {
          0: "Off",
          1: "Normal",
          2: "Low",
          3: "Boost",
          4: "Purge",
        };
        const BYPASS_MODES = {
          0: "Off",
          1: "Normal",
          2: "Evening fresh",
          3: "Night fresh",
        };
        const getKeyByValue = (obj, value) =>
          Number(Object.entries(obj).find(([, v]) => v === value)?.[0]);

        const afMode = getKeyByValue(MODES, selectMode.value);
        const bypassMode = getKeyByValue(BYPASS_MODES, selectBypassMode.value);

        payload = {
          // match HA service field names exactly
          indoor_temp: indoorTemp !== "" ? Number(indoorTemp) : undefined,
          outdoor_temp: outdoorTemp !== "" ? Number(outdoorTemp) : undefined,
          af_enp: afMode !== "" ? Number(afMode) : undefined,
          m_byp: bypassMode !== "" ? Number(bypassMode) : undefined,
        };

        // Remove undefined fields so HA doesn't get empty keys
        Object.keys(payload).forEach(
          (key) => payload[key] === undefined && delete payload[key],
        );

        if (this._hass && payload) {
          this._hass.callService("ventaxia_ha", "set_summer_bypass", payload);
        }

        // Hide the modal after saving
        modal.classList.add("hidden");
      } else {
        const from = modal.querySelector("#modal-from").value;
        const to = modal.querySelector("#modal-to").value;
        const mode = selectMode.value;
        const tsname = key;

        const inputs = Array.from(modal.querySelectorAll(".day-input"));
        const checkedValues = inputs
          .filter((i) => i.checked)
          .map((i) => i.value);

        const checkedShortNames = checkedValues.map(
          (day) => reverseDayMap[day] || day,
        );

        let daysToSave =
          checkedValues.length === Object.values(this.dayMap).length
            ? "Every day" // string if all days selected
            : checkedShortNames.join(", "); // comma-separated string otherwise

        payload = {
          name: key === "shrs" ? key : tsname,
          from: from,
          to: to,
          days: daysToSave,
          mode: mode,
        };

        if (this._hass && payload) {
          this._hass.callService(
            "ventaxia_ha",
            "update_schedule_or_silent_hours",
            payload,
          );
        }

        // Hide the modal after saving
        modal.classList.add("hidden");
      }
    });

    // Close modal
    closeBtn.addEventListener("click", () => modal.classList.add("hidden"));
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.add("hidden");
    });
  }
  getCardSize() {
    return 8;
  }
}

customElements.define("ventaxia-card", VentAxiaCard);
