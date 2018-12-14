#!/usr/bin/env dnsjit
if #arg < 2 then
    print("usage: "..arg[1].." <pcap> [<pcap> ...]")
    return
end

local dn_limit = 10
local ip = "127.0.0.1"
local port = "53121"

local stats = require("stats")
local psl = assert(require "psl".builtin())
local object = require("dnsjit.core.objects")
local input = require("dnsjit.input.pcap")
local layer = require("dnsjit.filter.layer")
local dns = require("dnsjit.core.object.dns").new()
local label = require("dnsjit.core.object.dns.label")

local labels = require("dnsjit.core.object.dns.label").new(127)
local q = require("dnsjit.core.object.dns.q").new()
local output = require("dnsjit.output.udpcli").new()

output:connect(ip, port)
local orecv, orctx = output:receive()

local unique = {}

local function add_unique(unique, qname, qtype, nlabels)
    if qname == nil or nlabels == nil then
        return
    end
    local reg_name = psl:registrable_domain(qname)
    local _, count
    if reg_name == nil then
        reg_name = "."
        count = 0
    else
        _, count = string.gsub(reg_name, "%.", ".")
        reg_name = string.lower(reg_name)  -- IN-aDDr.arPa. ->  in-addr.arpa.
    end
    nlabels = nlabels - count

    if unique[reg_name] == nil then
        unique[reg_name] = {}
    end
    if unique[reg_name][nlabels] == nil then
        unique[reg_name][nlabels] = {}
    end
    if unique[reg_name][nlabels][qtype] == nil then
        unique[reg_name][nlabels][qtype] = {}
        unique[reg_name][nlabels][qtype]["#count"] = 0
    end
    if unique[reg_name][nlabels][qtype]["#count"] < dn_limit then
        if unique[reg_name][nlabels][qtype][qname] == nil then
            unique[reg_name][nlabels][qtype][qname] = 1
            unique[reg_name][nlabels][qtype]["#count"] = unique[reg_name][nlabels][qtype]["#count"] + 1
            print(qname, reg_name, tonumber(nlabels), qtype)
            return true
        end
    end
    return false
end

local function process_packet(obj)
    dns.obj_prev = obj
    local ret = dns:parse_header()
    if ret == 0 and dns.qr == 0 and dns.qdcount > 0 and dns:parse_q(q, labels, 127) == 0 then
        local qnamestr, _ = label.tostring(dns, labels, 127)
        return add_unique(unique, qnamestr, dns.type_tostring(q.type), tonumber(q.labels))
    end
    return false
end

local function dn_counts(unique)
    local counts = {}
    -- extract unique[reg_name][nlabels][qtype]["#count"]
    for _, t2 in pairs(unique) do  -- reg_name
        for _, t3 in pairs(t2) do  -- nlabes
            for key, t4 in pairs(t3) do  -- qtype
                table.insert(counts, t4["#count"])
            end
        end
    end
    return counts
end

for n = 2, #arg do
    local pcap_input = input.new()
    pcap_input:open_offline(arg[n])
    local pcap_layer = layer.new()
    pcap_layer:producer(pcap_input)
    local producer, ctx = pcap_layer:produce()

    while true do
        local obj = producer(ctx)
        if obj == nil then break end
        local pl = obj:cast()
        if obj:type() == "payload" and pl.len > 0 then
            if process_packet(obj) then
                orecv:produce(orctx, obj)
            end
        end
    end
end

local counts = dn_counts(unique)

io.stderr:write(string.format("median dn_limit: %.2f\n", stats.median(counts)))
io.stderr:write(string.format("mean dn_limit: %.2f\n", stats.mean(counts)))
