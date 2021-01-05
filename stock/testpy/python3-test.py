# -*- encoding: utf-8 -*-
print("abc")

# fix bytes to str
# pytorch_gpu\lib\codecs.py
# def write(self, object):

#         """ Writes the object's contents encoded to self.stream.
#         """
#         data, consumed = self.encode(object, self.errors)
#         if isinstance(data,bytes):
#             data = data.decode()
#         self.stream.write(data)