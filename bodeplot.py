import sys, visa, numpy, math, time, serial
from enum import IntEnum
import matplotlib.pyplot as plot

class ScopeException(Exception):
    def __init__(self, message):
        super(ScopeException, self).__init__(message)

class Rigol:
    def __init__(self, ID):
        rm = visa.ResourceManager()
        resources = rm.list_resources()
        self.Interface = None
        for resource in resources:
            if 'USB' not in resource:
                continue
            interface = rm.open_resource(resource)
            identification = interface.query('*IDN?')
            if ID == identification.split(',')[1]:
                self.Interface = rm.open_resource(resource)
                break
    def __del__(self):
        if self.Interface != None:
            self.Interface.close()
    def Query(self, data):
        return self.Interface.query(data)
    def Write(self, data):
        self.Interface.write(data)
    def ReadRaw(self, data):
        return self.Interface.read_raw()
    def GetID(self):
        return self.Query('*IDN?')

class RigolSignalGenerator(Rigol):
    def __init__(self):
        super().__init__('DG1032Z')
    def __del__(self):
        super().__del__()
    def SetChannelFunc(self, channel, function):
        self.Write(':SOUR{0}:FUNC {1}'.format(channel, function))
    def SetChannelFreq(self, channel, freq):
        self.Write(':SOUR{0}:FREQ {1}'.format(channel, freq))
    def SetChannelON(self, channel):
        self.Write(':OUTP{0} ON'.format(channel))
    def SetChannelOFF(self, channel):
        self.Write(':OUTP{0} OFF'.format(channel))
    def SetArbritaryWaveform(self, channel, freq, waveform):
        self.Write(':SOUR{0}:APPL:ARB {1}'.format(channel, freq))
        wave = ':SOUR{0}:DATA VOLATILE,'.format(channel)
        for point in waveform:
            wave += str(point) + ','
        wave = wave.strip(',')
        self.Write(wave)

class RigolScope(Rigol):
    def __init__(self):
        super().__init__('DS1104Z')
    def __del__(self):
        super().__del__()
    def run(self):
        self.Write(':RUN')
    def stop(self):
        self.Write(':STOP')
    def single(self):
        self.Write(':SINGLE')

    def getMemoryDepth(self):
        return int(self.Query(':ACQ:MDEP?'))
    def setMemoryDepth(self, depth):
        self.Write(':ACQ:MDEP {0}'.format(depth))

    def getData(self,channel):
        data = []
        self.stop()
        memDepth = self.getMemoryDepth();
        self.Write(':WAV:FORM BYTE')
        self.Write(':WAV:MODE RAW')
        self.Write(':WAV:SOUR CHAN{0}'.format(channel))
        fullBatches = int(memDepth / 250000)
        for i in range(0,fullBatches+1):
            start = (i*250000)+1
            end = (i+1)*250000
            if end-start <= 0:
                continue
            if(end > memDepth):
                end = memDepth
            data = data + self.readRangeData(start,end)
        data = numpy.array(data)
        data -= self.getYOrigin(channel)
        data -= self.getYRef(channel)
        data *= self.getYINC(channel)
        return data

    def readRangeData(self,start,stop):
        self.Write(':WAV:STAR {0}'.format(start))
        self.Write(':WAV:STOP {0}'.format(stop))
        self.Write(':WAV:DATA?')
        dat = list(numpy.frombuffer(self.ReadRaw(),'B'))
        dat[0:12] = []
        del(dat[len(dat)-1])
        return dat

    def getVoltageScale(self,channel):
        return float(self.Query(':CHAN{0}:SCAL?'.format(channel)))
    def getVoltageOffset(self,channel):
        return float(self.Query(':CHAN{0}:OFFS?'.format(channel)))

    def getTimebase(self):
        return float(self.Query(':TIM:SCAL?'))
    def getTimeOffset(self):
        return float(self.Query(':TIM:OFFS?'))

    def getYOrigin(self,channel):
        self.Write(':WAV:SOUR CHAN{0}'.format(channel))
        return float(self.Query(':WAV:YOR?'))
    def getYRef(self,channel):
        self.Write(':WAV:SOUR CHAN{0}'.format(channel))
        return float(self.Query(':WAV:YREF?'))
    def getYINC(self,channel):
        self.Write(':WAV:SOUR CHAN{0}'.format(channel))
        return float(self.Query(':WAV:YINC?'))

    def query(self,queryStr):
        return self.Query(queryStr)

    measurementCommands = {
        'VMAX': 'VMAX',
        'VMIN': 'VMIN',
        'VPP': 'VPP',
        'VTOP': 'VTOP',
        'VBASe': 'VBASe',
        'VAMP': 'VAMP',
        'VAVG': 'VAVG',
        'VRMS': 'VRMS',
        'OVERSHOOT': 'OVERshoot',
        'PRESHOOT': 'PREShoot',
        'AREA': 'MARea',
        'PER AREA': 'MPARea',
        'PERIOD': 'PERiod',
        'FREQUENCY': 'FREQuency',
        'RISE TIME': 'RTIMe',
        'FALL TIME': 'FTIMe',
        '+WIDTH': 'PWIDth',
        '-WIDTH': 'NWIDth',
        '+DUTY': "PDUTy",
        'RDELAY': 'RDELay',
        'FPHASE': 'FPHase',
        'TVMAX': 'TVMAX',
        'TVMIN': 'TVMIN',
        '+RATE': 'PSLEWrate',
        '-RATE': 'NSLEWrate',
        'VUPPER': 'VUPper',
        'VMID': 'VMID',
        'VLOWER': 'VLOWer',
        'VARIANCE': 'VARIance',
        'PER VRMS': 'PVRMS',
        '+PULSES': 'PPULses',
        '-PULSES': 'NPULses',
        '+EDGES': 'PEDGes',
        '-EDGES': 'NEDGes'
    }
    def getMeasurementItem(self,measurement):
        if measurement in self.measurementCommands.values():
            return measurement
        if measurement.upper() in self.measurementCommands.keys():
            return self.measurementCommands[measurement.upper()]
        raise ScopeException("ERROR MEASURMENT: {0} NOT FOUND".format(measurement))
    def getMeasurement(self, measurement,channel):
        measurementStr = self.getMeasurementItem(measurement)
        measurement = self.Query(':MEASure:ITEM? {0},CHANnel{1}'.format(measurementStr,channel))
        self.Write(':MEASure:CLEar ALL')
        return measurement
    def getFrequency(self, channel):
        self.Write(':MEASure:COUNter:SOURce  CHANnel{0}'.format(channel))
        return float(self.Query(':MEASure:COUNter:VALue?'))


scope = RigolScope()
signalGenerator = RigolSignalGenerator()

print("Enter Channel 2 gain relative to Channel 1: ")
multFactor = float(input())

# waveform = []
# points = 100
# for i in range(0, points):
#     point = 0.5 * (math.cos(i * (2*math.pi / points)) + math.cos(i * 2 *(2*math.pi / points)))
#     waveform.append(point)

# signalGenerator.SetArbritaryWaveform(1, 1000, waveform)
# signalGenerator.SetChannelON(1)


signalGenerator.SetChannelFunc(1,'SIN')
signalGenerator.SetChannelON(1)

# Frequency steps 1 Hz to 8 kHz in 100 Hz increments
freqs = range(1, 8000, 100)

dataPoints = []

for i in freqs:
    signalGenerator.SetChannelFreq(1, i)
    time.sleep(1)

    freq = float(scope.getFrequency(1))
    vpp1 = float(scope.getMeasurement('VPP',1))
    vpp2 = float(scope.getMeasurement('VPP',2)) * multFactor
    print("Frequency:")
    print('\t'+str(freq))
    print("VPP: 1")
    print('\t'+str(vpp1))
    print("VPP: 2")
    print('\t'+str(vpp2))

    gain = vpp2 / vpp1
    print("Gain: ")
    print('\t'+str(gain))

    attenuation = 20 * math.log(gain,10)
    print("Attenuation: ")
    print('\t'+str(attenuation)+'db')
    dataPoints.append([freq, vpp1, vpp2, gain, attenuation])


with open('output.csv', 'w') as f:
    f.write('Frequency, CH1 VPP, CH2 VPP, Gain, Attenuation (dB)\n')
    for point in dataPoints:
        f.write('{0}, {1}, {2}, {3}, {4}\n'.format(point[0], point[1], point[2], point[3], point[4]))