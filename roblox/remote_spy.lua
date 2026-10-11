--[[
    Remote Spy
    Zeichnet jeden FireServer/InvokeServer-Aufruf des Spiels auf und zeigt
    Remote + Argumente in einem Fenster an.

    So benutzen:
      1. Skript ausführen
      2. Zum Creaking Egg gehen und einmal E drücken (Ei öffnen)
      3. Optional: Halloween Chest öffnen, einmal Trick or Treat machen
      4. "Kopieren" drücken und das Ergebnis schicken
]]

local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")

-- Remotes, deren Pfad eines dieser Wörter enthält, werden ignoriert
-- (z. B. Bewegungs-/Maus-Updates, die jede Sekunde feuern). Bei Spam erweitern.
local IGNORE = { "mouse", "camera", "move", "ping", "heartbeat" }
local MAX_ENTRIES = 150

------------------------------------------------------------------------

if typeof(hookmetamethod) ~= "function" or typeof(getnamecallmethod) ~= "function" then
    error("Dein Executor unterstützt hookmetamethod/getnamecallmethod nicht – Remote Spy nicht möglich")
end
local wrap = typeof(newcclosure) == "function" and newcclosure or function(f) return f end
local isOwnCall = typeof(checkcaller) == "function" and checkcaller or function() return false end

local entries = {}
local paused = false
local refresh = function() end

local function serialize(value, depth)
    depth = depth or 0
    local t = typeof(value)
    if t == "string" then
        return string.format("%q", value)
    elseif t == "Instance" then
        local ok, name = pcall(function() return value:GetFullName() end)
        return ok and name or "<Instance>"
    elseif t == "table" then
        if depth >= 3 then return "{...}" end
        local parts = {}
        for k, v in pairs(value) do
            table.insert(parts, "[" .. serialize(k, depth + 1) .. "] = " .. serialize(v, depth + 1))
            if #parts >= 25 then table.insert(parts, "...") break end
        end
        return "{" .. table.concat(parts, ", ") .. "}"
    elseif t == "number" or t == "boolean" or t == "nil" then
        return tostring(value)
    else
        return t .. ".new(" .. tostring(value) .. ")"
    end
end

local function isIgnored(path)
    local lower = string.lower(path)
    for _, word in ipairs(IGNORE) do
        if string.find(lower, word, 1, true) then return true end
    end
    return false
end

local function logCall(remote, method, args)
    if paused then return end
    local ok, path = pcall(function() return remote:GetFullName() end)
    path = ok and path or "<unbekannt>"
    if isIgnored(path) then return end

    local parts = {}
    for i = 1, args.n do
        parts[i] = serialize(args[i])
    end
    local line = string.format("[%s] %s  (%s)", method, path, table.concat(parts, ", "))

    -- Gleiche Aufrufe direkt hintereinander zusammenfassen
    local last = entries[#entries]
    if last and last.line == line then
        last.count += 1
    else
        table.insert(entries, { line = line, count = 1 })
        if #entries > MAX_ENTRIES then table.remove(entries, 1) end
    end
    refresh()
end

local oldNamecall
oldNamecall = hookmetamethod(game, "__namecall", wrap(function(self, ...)
    local method = getnamecallmethod()
    if (method == "FireServer" or method == "InvokeServer") and not isOwnCall() then
        local args = table.pack(...)
        task.spawn(logCall, self, method, args)
    end
    return oldNamecall(self, ...)
end))

------------------------------------------------------------------------
-- Fenster
------------------------------------------------------------------------

local parent
if typeof(gethui) == "function" then pcall(function() parent = gethui() end) end
if not parent then pcall(function() parent = game:GetService("CoreGui") end) end

local screen = Instance.new("ScreenGui")
screen.Name = "RemoteSpyGui"
screen.ResetOnSpawn = false
screen.DisplayOrder = 1000
if not (parent and pcall(function() screen.Parent = parent end) and screen.Parent) then
    screen.Parent = Players.LocalPlayer:WaitForChild("PlayerGui")
end

local frame = Instance.new("Frame")
frame.Size = UDim2.fromOffset(460, 320)
frame.Position = UDim2.new(1, -480, 0.3, 0)
frame.BackgroundColor3 = Color3.fromRGB(25, 25, 30)
frame.BorderSizePixel = 0
frame.Parent = screen
Instance.new("UICorner", frame).CornerRadius = UDim.new(0, 8)

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, -20, 0, 30)
title.Position = UDim2.fromOffset(10, 0)
title.BackgroundTransparency = 1
title.TextXAlignment = Enum.TextXAlignment.Left
title.Font = Enum.Font.GothamBold
title.TextSize = 14
title.TextColor3 = Color3.fromRGB(255, 160, 40)
title.Text = "Remote Spy – drück jetzt E am Ei"
title.Parent = frame

local function button(text, index, color)
    local b = Instance.new("TextButton")
    b.Size = UDim2.fromOffset(100, 24)
    b.Position = UDim2.fromOffset(10 + (index - 1) * 108, 32)
    b.BackgroundColor3 = color
    b.TextColor3 = Color3.new(1, 1, 1)
    b.Font = Enum.Font.GothamBold
    b.TextSize = 12
    b.Text = text
    b.Parent = frame
    Instance.new("UICorner", b).CornerRadius = UDim.new(0, 6)
    return b
end

local copyBtn = button("Kopieren", 1, Color3.fromRGB(46, 120, 200))
local pauseBtn = button("Pause", 2, Color3.fromRGB(90, 90, 110))
local clearBtn = button("Leeren", 3, Color3.fromRGB(90, 90, 110))
local closeBtn = button("Schließen", 4, Color3.fromRGB(170, 50, 50))

local scroll = Instance.new("ScrollingFrame")
scroll.Size = UDim2.new(1, -20, 1, -66)
scroll.Position = UDim2.fromOffset(10, 60)
scroll.BackgroundColor3 = Color3.fromRGB(15, 15, 18)
scroll.BorderSizePixel = 0
scroll.ScrollBarThickness = 8
scroll.AutomaticCanvasSize = Enum.AutomaticSize.Y
scroll.CanvasSize = UDim2.new()
scroll.Parent = frame

local box = Instance.new("TextBox")
box.Size = UDim2.new(1, -12, 0, 0)
box.AutomaticSize = Enum.AutomaticSize.Y
box.BackgroundTransparency = 1
box.ClearTextOnFocus = false
box.TextEditable = false
box.MultiLine = true
box.TextWrapped = true
box.TextXAlignment = Enum.TextXAlignment.Left
box.TextYAlignment = Enum.TextYAlignment.Top
box.Font = Enum.Font.Code
box.TextSize = 12
box.TextColor3 = Color3.fromRGB(220, 220, 220)
box.Text = "(noch keine Aufrufe)"
box.Parent = scroll

local function fullText()
    local out = {}
    for _, e in ipairs(entries) do
        table.insert(out, e.count > 1 and (e.line .. "  x" .. e.count) or e.line)
    end
    return table.concat(out, "\n")
end

local pending = false
refresh = function()
    if pending then return end
    pending = true
    task.delay(0.2, function()
        pending = false
        if box.Parent then
            box.Text = #entries > 0 and fullText() or "(noch keine Aufrufe)"
            scroll.CanvasPosition = Vector2.new(0, 1e6)
        end
    end)
end

copyBtn.MouseButton1Click:Connect(function()
    if typeof(setclipboard) == "function" then
        setclipboard(fullText())
        copyBtn.Text = "Kopiert!"
        task.delay(1.5, function() copyBtn.Text = "Kopieren" end)
    else
        copyBtn.Text = "nicht verfügbar"
    end
end)
pauseBtn.MouseButton1Click:Connect(function()
    paused = not paused
    pauseBtn.Text = paused and "Weiter" or "Pause"
end)
clearBtn.MouseButton1Click:Connect(function()
    table.clear(entries)
    refresh()
end)
closeBtn.MouseButton1Click:Connect(function()
    paused = true -- Hook bleibt aktiv, zeichnet aber nichts mehr auf
    screen:Destroy()
end)

-- Fenster an der Titelleiste verschieben
local dragging, dragStart, startPos
title.InputBegan:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.MouseButton1
        or input.UserInputType == Enum.UserInputType.Touch then
        dragging, dragStart, startPos = true, input.Position, frame.Position
        input.Changed:Connect(function()
            if input.UserInputState == Enum.UserInputState.End then dragging = false end
        end)
    end
end)
UserInputService.InputChanged:Connect(function(input)
    if dragging and (input.UserInputType == Enum.UserInputType.MouseMovement
        or input.UserInputType == Enum.UserInputType.Touch) then
        local d = input.Position - dragStart
        frame.Position = UDim2.new(startPos.X.Scale, startPos.X.Offset + d.X, startPos.Y.Scale, startPos.Y.Offset + d.Y)
    end
end)
