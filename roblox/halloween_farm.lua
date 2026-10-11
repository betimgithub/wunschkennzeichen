--[[
    Halloween Farm
    1) Trick or Treat: läuft alle gespawnten "Trick or Treat!"-Flächen ab,
       bleibt auf jeder stehen, bis "Come back soon" erscheint, und geht
       dann zur nächsten. Flächen im Cooldown werden übersprungen und
       besucht, sobald sie wieder bereit sind.
    2) Auto-Hatch: öffnet parallel (task.spawn) "Creaking Egg" und
       "Halloween Chest" im Hintergrund.

    Stoppen:  _G.HalloweenFarmRun = nil
    Erneutes Ausführen beendet automatisch die alte Instanz.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local player = Players.LocalPlayer

------------------------------------------------------------------------
-- KONFIGURATION
------------------------------------------------------------------------
local CONFIG = {
    TrickOrTreat = {
        Enabled = true,
        ReadyText = "trick or treat",    -- Text, wenn die Fläche bereit ist
        CooldownText = "come back soon", -- Text nach dem Klopfen
        MinStandTime = 3,                -- Animation dauert ca. 3 Sekunden
        MaxStandTime = 10,               -- Abbruch, falls "Come back soon" nie kommt
        SkipFailedFor = 30,              -- fehlgeschlagene Fläche so lange ignorieren (s)
        HeightOffset = 3,                -- Abstand über der Fläche beim Teleport
        ScanDelay = 1,                   -- Pause, wenn gerade keine Fläche bereit ist
        Debug = true,                    -- gefundene Flächen im Output anzeigen
    },

    Hatch = {
        Enabled = true,
        -- "Remote": feuert ein RemoteEvent / ruft eine RemoteFunction auf
        -- "Prompt": löst den E-ProximityPrompt direkt aus (braucht fireproximityprompt)
        Mode = "Remote",

        -- Nur für Mode = "Remote": Pfad ab ReplicatedStorage
        -- z. B. ReplicatedStorage.Remotes.HatchEgg -> { "Remotes", "HatchEgg" }
        RemotePath = { "REMOTE_ORDNER", "REMOTE_NAME" },

        -- Was geöffnet werden soll. Nicht gewünschte Einträge einfach löschen.
        Targets = { "Creaking Egg", "Halloween Chest" },

        -- Zusätzliche Argumente nach dem Namen, z. B. { 1 } für die Anzahl.
        -- Gesendet wird: FireServer("Creaking Egg", table.unpack(ExtraArgs))
        ExtraArgs = {},

        Interval = 1,   -- Sekunden zwischen zwei Aufrufen
        Verbose = false,
    },
}
------------------------------------------------------------------------

local runId = (_G.HalloweenFarmRun or 0) + 1
_G.HalloweenFarmRun = runId
local function running()
    return _G.HalloweenFarmRun == runId
end

local function log(...)
    print("[HalloweenFarm]", ...)
end

------------------------------------------------------------------------
-- Trick or Treat
------------------------------------------------------------------------

local function textOf(obj)
    if obj:IsA("TextLabel") or obj:IsA("TextButton") then
        local t = obj.ContentText ~= "" and obj.ContentText or obj.Text
        return string.lower(t)
    end
end

-- Liest alle sichtbaren Texte eines BillboardGuis aus
local function guiState(gui)
    local ready, cooldown = false, false
    if not gui.Parent or not gui.Enabled then
        return false, false
    end
    for _, obj in ipairs(gui:GetDescendants()) do
        local t = textOf(obj)
        if t and obj.Visible then
            if string.find(t, CONFIG.TrickOrTreat.ReadyText, 1, true) then ready = true end
            if string.find(t, CONFIG.TrickOrTreat.CooldownText, 1, true) then cooldown = true end
        end
    end
    return ready and not cooldown, cooldown
end

local function firstPart(model)
    return model.PrimaryPart or model:FindFirstChildWhichIsA("BasePart", true)
end

-- Findet das Teil, auf das man sich stellen muss
local function partForGui(gui)
    local adornee = gui.Adornee
    if adornee then
        if adornee:IsA("BasePart") then return adornee end
        if adornee:IsA("Attachment") then return adornee.Parent end
        if adornee:IsA("Model") then return firstPart(adornee) end
    end
    local parent = gui.Parent
    while parent and parent ~= workspace and parent ~= game do
        if parent:IsA("BasePart") then return parent end
        if parent:IsA("Attachment") and parent.Parent:IsA("BasePart") then return parent.Parent end
        if parent:IsA("Model") then return firstPart(parent) end
        parent = parent.Parent
    end
end

-- Sucht alle Trick-or-Treat-BillboardGuis (Workspace + PlayerGui)
local function scanPads()
    local pads, seen = {}, {}
    local roots = { workspace, player:FindFirstChildOfClass("PlayerGui") }
    for _, root in ipairs(roots) do
        for _, obj in ipairs(root:GetDescendants()) do
            local t = textOf(obj)
            if t and (string.find(t, CONFIG.TrickOrTreat.ReadyText, 1, true)
                or string.find(t, CONFIG.TrickOrTreat.CooldownText, 1, true)) then
                local gui = obj:FindFirstAncestorWhichIsA("BillboardGui")
                    or obj:FindFirstAncestorWhichIsA("SurfaceGui")
                if gui and not seen[gui] then
                    seen[gui] = true
                    local part = partForGui(gui)
                    if part then
                        table.insert(pads, { gui = gui, part = part })
                    end
                end
            end
        end
    end
    return pads
end

local function standPosition(part)
    return part.Position + Vector3.new(0, part.Size.Y / 2 + CONFIG.TrickOrTreat.HeightOffset, 0)
end

local failedUntil = {}

local function visitPad(pad, hrp)
    local cfg = CONFIG.TrickOrTreat
    local target = standPosition(pad.part)
    local radius = math.max(math.min(pad.part.Size.X, pad.part.Size.Z) / 2, 2)

    hrp.CFrame = CFrame.new(target)
    hrp.AssemblyLinearVelocity = Vector3.zero

    local start = os.clock()
    while running() and hrp.Parent do
        local elapsed = os.clock() - start
        local _, cooldown = guiState(pad.gui)

        if cooldown and elapsed >= cfg.MinStandTime then
            if cfg.Debug then log(string.format("fertig: %s (%.1fs)", pad.part:GetFullName(), elapsed)) end
            return
        end
        if elapsed >= cfg.MaxStandTime or not pad.gui.Parent then
            warn("[HalloweenFarm] kein 'Come back soon' bei " .. pad.part:GetFullName() .. " – übersprungen")
            failedUntil[pad.gui] = os.clock() + cfg.SkipFailedFor
            return
        end

        -- Auf der Fläche bleiben, falls man runterfällt oder weggeschoben wird
        local offset = hrp.Position - target
        if Vector3.new(offset.X, 0, offset.Z).Magnitude > radius then
            hrp.CFrame = CFrame.new(target)
            hrp.AssemblyLinearVelocity = Vector3.zero
        end
        task.wait(0.2)
    end
end

local function trickOrTreatLoop()
    local cfg = CONFIG.TrickOrTreat
    local announced = false
    while running() do
        local char = player.Character
        local hrp = char and char:FindFirstChild("HumanoidRootPart")
        local humanoid = char and char:FindFirstChildOfClass("Humanoid")
        if not hrp or not humanoid or humanoid.Health <= 0 then
            task.wait(1)
            continue
        end

        local all = scanPads()
        if cfg.Debug and not announced then
            log(#all .. " Trick-or-Treat-Flächen gefunden")
            for _, pad in ipairs(all) do log("  " .. pad.part:GetFullName()) end
            announced = true
        end

        -- Nur bereite Flächen, die nicht gerade gesperrt sind
        local now = os.clock()
        local ready = {}
        for _, pad in ipairs(all) do
            if (failedUntil[pad.gui] or 0) < now and (guiState(pad.gui)) then
                table.insert(ready, pad)
            end
        end

        if #ready == 0 then
            task.wait(cfg.ScanDelay)
            continue
        end

        -- Nächstgelegene zuerst -> kurze Wege durch die ganze Zone
        table.sort(ready, function(a, b)
            return (a.part.Position - hrp.Position).Magnitude < (b.part.Position - hrp.Position).Magnitude
        end)
        visitPad(ready[1], hrp)
    end
end

------------------------------------------------------------------------
-- Auto-Hatch
------------------------------------------------------------------------

local function resolveRemote(path)
    local current = ReplicatedStorage
    for _, name in ipairs(path) do
        current = current:WaitForChild(name, 10)
        if not current then
            return nil, "nicht gefunden: " .. name
        end
    end
    return current
end

-- Sucht den ProximityPrompt (E-Taste) eines Eies / einer Chest
local function findPrompt(targetName)
    local lowerTarget = string.lower(targetName)
    for _, obj in ipairs(workspace:GetDescendants()) do
        if obj:IsA("ProximityPrompt") then
            local haystack = string.lower(obj.ObjectText .. " " .. obj.ActionText .. " " .. obj:GetFullName())
            if string.find(haystack, lowerTarget, 1, true) then
                return obj
            end
        end
    end
end

local function hatchLoop()
    local cfg = CONFIG.Hatch
    local fire

    if cfg.Mode == "Prompt" then
        if typeof(fireproximityprompt) ~= "function" then
            warn("[HalloweenFarm] fireproximityprompt nicht verfügbar – nutze Mode = \"Remote\"")
            return
        end
        local prompts = {}
        fire = function(target)
            local prompt = prompts[target]
            if not prompt or not prompt.Parent then
                prompt = findPrompt(target)
                prompts[target] = prompt
            end
            if not prompt then error("kein ProximityPrompt für " .. target) end
            fireproximityprompt(prompt)
        end
    else
        local remote, err = resolveRemote(cfg.RemotePath)
        if not remote then
            warn("[HalloweenFarm] Remote " .. err)
            return
        end
        local isFunction = remote:IsA("RemoteFunction")
        log("Auto-Hatch über " .. remote:GetFullName())
        fire = function(target)
            if isFunction then
                return remote:InvokeServer(target, table.unpack(cfg.ExtraArgs))
            end
            remote:FireServer(target, table.unpack(cfg.ExtraArgs))
        end
    end

    while running() do
        for _, target in ipairs(cfg.Targets) do
            if not running() then break end
            local ok, result = pcall(fire, target)
            if not ok then
                warn("[HalloweenFarm] Hatch-Fehler (" .. target .. "): " .. tostring(result))
            elseif cfg.Verbose then
                log("Hatch gesendet: " .. target .. (result ~= nil and (" -> " .. tostring(result)) or ""))
            end
            task.wait(cfg.Interval)
        end
    end
end

------------------------------------------------------------------------
-- Start
------------------------------------------------------------------------

if CONFIG.Hatch.Enabled then
    task.spawn(hatchLoop)
end
if CONFIG.TrickOrTreat.Enabled then
    task.spawn(trickOrTreatLoop)
end
log("gestartet (Stoppen: _G.HalloweenFarmRun = nil)")
